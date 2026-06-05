import os
import asyncio
import json
from urllib.parse import urlparse
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from SaraAgent.providers import LLMProvider, LLMResponse, ProviderSpec, ToolCallRequest


if TYPE_CHECKING:
    from openai import AsyncOpenAI as AsyncOpenAIType

AsyncOpenAI: Any = None

def _get(obj: Any, key: str) -> Any:
    """Get a value from dict or object attribute, returning None if absent."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

def _is_local_endpoint(spec: ProviderSpec | None, base_url: str | None) -> bool:
    if spec and spec.is_local:
        return True
    if not base_url:
        return False
    raw = base_url.strip().lower()
    parsed = urlparse(raw if "://" in raw else f"//{raw}") 
    try:
        host = parsed.hostname
    except ValueError:
        return False
    if host in {"localhost", "host.docker.internal"}:
        return True
    if not host:
        return False

class OpenaiCompactProvider(LLMProvider):
    def __init__(
            self,
            api_key: str | None = None,
            base_url: str | None = None,
            default_model: str = "gpt-4o",
            spec: ProviderSpec | None = None,
        ):
        super().__init__(api_key, base_url)
        self.default_model = default_model
        self._spec = spec

        if api_key and spec and spec.env_key:
             self._setup_env(api_key, base_url)
        effective_base = base_url or (spec.default_api_base if spec else None) or None
        self._effective_base = effective_base
        self._api_key_for_client = api_key or "no-key"
        self._is_local = _is_local_endpoint(spec, effective_base)
        self._client: AsyncOpenAIType | None = None
        self._client_lock = asyncio.Lock()
    
    def _setup_env(self, api_key: str, api_base: str | None) -> None:
        """Set environment variables based on provider spec."""
        spec = self._spec
        if not spec or not spec.env_key:
            return
        if spec.is_gateway:
            os.environ[spec.env_key] = api_key
        else:
            os.environ.setdefault(spec.env_key, api_key)
        
    def _build_client(self):
        import httpx
        http_client: httpx.AsyncClient | None = None

        if self._is_local:
            http_client = httpx.AsyncClient(
                limits=httpx.Limits(keepalive_expiry=0),
                timeout=160,
            )
        self._client = AsyncOpenAI(
            api_key=self._api_key_for_client,
            base_url=self._effective_base,
            max_retries=0,
            timeout=160,
            http_client=http_client,
        )
    
    async def _get_client(self):
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is not None:
                return self._client
            global AsyncOpenAI
            if AsyncOpenAI is None:
                from openai import AsyncOpenAI as _AsyncOpenAI
                AsyncOpenAI = _AsyncOpenAI

            self._build_client()
            return self._client
        
    def _parse(self, response: Any) -> LLMResponse:
        if(isinstance(response, str)):
            return LLMResponse(content=response, finish_reason="stop")
        
        choice = response.choices[0]
        msg = choice.message
        content = msg.content
        finish_reason = str(choice.finish_reason or "stop")

        raw_tool_calls: list[Any] = []
        for ch in response.choices:
            m = ch.message
            if hasattr(m, "tool_calls") and m.tool_calls:
                raw_tool_calls.extend(m.tool_calls)
                if ch.finish_reason in ("tool_calls", "stop"):
                    finish_reason = ch.finish_reason
            if not content and m.content:
                content = m.content
            # if not content and getattr(m, "reasoning", None) and self._spec and self._spec.reasoning_as_content:
            #     content = m.reasoning

        parsed_tool_calls = []
        for tc in raw_tool_calls:
            fn = getattr(tc, "function", None) or {}
            args = getattr(fn, "arguments", None) or {}
            if isinstance(args, str):
                args = json.loads(args)
            parsed_tool_calls.append(ToolCallRequest(
                id=getattr(tc, "id", ""),
                name=getattr(fn, "name", ""),
                arguments=args,
                extra_content=getattr(tc, "extra_content", None) or None,
                provider_specific_fields=getattr(tc, "provider_specific_fields", None) or None,
                function_provider_specific_fields=getattr(fn, "provider_specific_fields", None) or None,
            ))

        reasoning_content = getattr(msg, "reasoning_content", None) or None
        if not reasoning_content and getattr(msg, "reasoning", None):
            reasoning_content = msg.reasoning


        return LLMResponse(
            content=content,
            finish_reason=finish_reason,
            tool_calls=parsed_tool_calls,
        )
    
    @staticmethod
    def _maybe_mapping(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        return None
    
    @classmethod
    def _extract_usage(cls, response: Any) -> dict[str, int]:
        """Extract token usage from an OpenAI-compatible response.

        Handles both dict-based (raw JSON) and object-based (SDK Pydantic)
        responses.  Provider-specific ``cached_tokens`` fields are normalised
        under a single key; see the priority chain inside for details.
        """
        # --- resolve usage object ---
        usage_obj = None
        response_map = cls._maybe_mapping(response)
        if response_map is not None:
            usage_obj = response_map.get("usage")
        elif hasattr(response, "usage") and response.usage:
            usage_obj = response.usage

        usage_map = cls._maybe_mapping(usage_obj)
        if usage_map is not None:
            result = {
                "prompt_tokens": int(usage_map.get("prompt_tokens") or 0),
                "completion_tokens": int(usage_map.get("completion_tokens") or 0),
                "total_tokens": int(usage_map.get("total_tokens") or 0),
            }
        elif usage_obj:
            result = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
            }
        else:
            return {}
    
    @classmethod
    def _parse_chunks(cls, chunks: list[Any]) -> LLMResponse:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tc_bufs: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        usage: dict[str, int] = {}

        def _accum_tool_calls(tc: Any, idx_hint: int) -> None:
            tc_idx = _get(tc, "index") if _get(tc, "index") is not None else idx_hint
            buf = tc_bufs.setdefault(tc_idx, {
                "id": "", "name": "", "arguments": "",
                "extra_content": None, "prov": None, "fn_prov": None,
            })
            tc_id = _get(tc, "id")
            if tc_id:
                buf["id"] = str(tc_id)
            
            fn = _get(tc, "function")
            if fn is not None:
                fn_name = _get(fn, "name")
                if fn_name:
                    buf["name"] = str(fn_name)
                fn_args = _get(fn, "arguments")
                if fn_args:
                    buf["arguments"] += str(fn_args)
        
        def _accum_legacy_function_call(function_call: Any) -> None:
            """Accumulate legacy ``delta.function_call`` streaming chunks."""
            if not function_call:
                return
            buf = tc_bufs.setdefault(0, {
                "id": "", "name": "", "arguments": "",
                "extra_content": None, "prov": None, "fn_prov": None,
            })
            fn_name = _get(function_call, "name")
            if fn_name:
                buf["name"] = str(fn_name)
            fn_args = _get(function_call, "arguments")
            if fn_args:
                buf["arguments"] += str(fn_args)


        for chunk in chunks:
            if isinstance(chunk, str):
                content_parts.append(chunk)
                continue

            chunk_map = cls._maybe_mapping(chunk)
            if not chunk_map:
                print("if not chunk_map")

            if not chunk.choices:
                usage = cls._extract_usage(chunk) or usage
                continue

            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta
            if delta and delta.content:
                content_parts.append(delta.content)
            if delta:
                reasoning = getattr(delta, "reasoning_content", None)
                if not reasoning:
                    reasoning = getattr(delta, "reasoning", None)
                if reasoning:
                    reasoning_parts.append(reasoning)

            for tc in (getattr(delta, "tool_calls", None) or []) if delta else []:
                _accum_tool_calls(tc, getattr(tc, "index", 0))
            if delta:
                _accum_legacy_function_call(getattr(delta, "function_call", None))

        return LLMResponse(
            content="".join(content_parts) or None,
            tool_calls=[
                ToolCallRequest(
                    id=b["id"],
                    name=b["name"],
                    arguments=json.loads(b["arguments"]) if b["arguments"] else {},
                    extra_content=b.get("extra_content"),
                    provider_specific_fields=b.get("prov"),
                    function_provider_specific_fields=b.get("fn_prov"),
                )
                for b in tc_bufs.values()
            ],
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content="".join(reasoning_parts) or None,
        ) 
            
        
    
    async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        
        await self._get_client()
        try:
            # kwargs = self._build_kwargs(
            #         messages, tools, model, max_tokens, temperature,
            #         reasoning_effort, tool_choice,
            #     )
            response = await self._client.chat.completions.create(
                model=model or self.default_model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return self._parse(response)
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {e}") from e
        
    async def chat_stream(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta: Callable[[str], Awaitable[None]] | None = None,
            on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        await self._get_client()
        try:
            # kwargs = self._build_kwargs(
            #         messages, tools, model, max_tokens, temperature,
            #         reasoning_effort, tool_choice,
            #     )
            stream = await self._client.chat.completions.create(
                model=model or self.default_model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                stream_options={"include_usage": True},
            )
            chunks: list[Any] = []
            stream_iter = stream.__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        stream_iter.__anext__(),
                        timeout=30,
                    )
                except StopAsyncIteration:
                    break
                chunks.append(chunk)
                if(chunk.choices):
                    delta_obj = chunk.choices[0].delta
                    if on_content_delta:
                        text = getattr(delta_obj, "content", None)
                        if text:
                            await on_content_delta(text)
                    if on_thinking_delta:
                        reasoning = getattr(delta_obj, "reasoning", None)
                        if reasoning:
                            await on_thinking_delta(reasoning)
                
            return self._parse_chunks(chunks)

        except asyncio.TimeoutError:
            return LLMResponse(
                content=(
                    f"Error calling LLM: stream stalled for more than "
                    # f"{idle_timeout_s} seconds"
                ),
                finish_reason="error",
                error_kind="timeout",
            )








