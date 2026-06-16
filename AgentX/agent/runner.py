from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os
import asyncio
from loguru import logger
from contextlib import suppress


from AgentX.providers import LLMProvider, LLMResponse, ToolCallRequest
from AgentX.agent.hook import AgentHookContext
from AgentX.tools.registry import ToolRegistry
from AgentX.utils.helpers import build_assistant_message, truncate_text

_DEFAULT_ERROR_MESSAGE = "Sorry, I encountered an error calling the AI model."
_MAX_LENGTH_RECOVERIES = 3

@dataclass(slots=True)
class AgentRunSpec:
    """Configuration for a single agent execution."""

    initial_messages: list[dict[str, Any]]
    tools: ToolRegistry
    model: str
    max_iterations: int
    max_tool_result_chars: int
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning_effort: str | None = None
    # hook: AgentHook | None = None
    error_message: str | None = _DEFAULT_ERROR_MESSAGE
    max_iterations_message: str | None = None
    concurrent_tools: bool = False
    stream_progress_deltas: bool = True
    llm_timeout_s: float | None = None

@dataclass(slots=True)
class AgentRunResult:
    """Outcome of a shared agent execution."""

    final_content: str | None
    messages: list[dict[str, Any]]
    tools_used: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "completed"
    error: str | None = None
    tool_events: list[dict[str, str]] = field(default_factory=list)
    had_injections: bool = False

class AgentRunner:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def run(
            self,
            spec: AgentRunSpec,
        ) -> AgentRunResult:
        messages = list(spec.initial_messages)
        final_content: str | None = None
        tools_used: list[str] = []
        usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        error: str | None = None
        stop_reason = "completed"
        tool_events: list[dict[str, str]] = []

        for iteration in range(spec.max_iterations):
            context = AgentHookContext(iteration=iteration, messages=messages)
            response = await self._request_model(spec, messages)
            raw_usage = self._usage_dict(response.usage)
            context.response = response
            context.tool_calls = list(response.tool_calls)
            self._accumulate_usage(usage, raw_usage)

            if response.should_execute_tools:
                context.tool_calls = list(response.tool_calls)

                assistant_msg = build_assistant_message(
                    content=response.content,
                    tool_calls=[tc.to_openai_tool_call() for tc in response.tool_calls],
                    reasoning_content=response.reasoning_content,
                    # thinking_blocks=response.thinking_blocks,
                )

                messages.append(assistant_msg)
                tools_used.extend(tc.name for tc in response.tool_calls)

                results, new_events, fatal_error = await self._execute_tools(
                        spec,
                        response.tool_calls,
                    )
                
                print(results, new_events, fatal_error)
                tool_events.extend(new_events)
                context.tool_results = list(results)
                context.tool_events = list(new_events)
                completed_tool_results: list[dict[str, Any]] = []
                for tool_call, result in zip(response.tool_calls, results):
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": self._normalize_tool_result(
                                spec,
                                tool_call.id,
                                tool_call.name,
                                result,
                            ),
                        }
                        messages.append(tool_message)
                        completed_tool_results.append(tool_message)

                if fatal_error is not None:
                        error = f"Error: {type(fatal_error).__name__}: {fatal_error}"
                        final_content = error
                        stop_reason = "tool_error"
                        self._append_final_message(messages, final_content)
                        context.final_content = final_content
                        context.error = error
                        context.stop_reason = stop_reason
                
                continue
            
            if response.has_tool_calls:
                logger.warning(
                    "Ignoring tool calls under finish_reason='{}'", ## add {} is session
                    response.finish_reason,
                    # spec.session_key or "default",
                )

            if response.finish_reason == "length":
                length_recovery_count += 1
                if length_recovery_count <= _MAX_LENGTH_RECOVERIES:
                    logger.info(
                        "Output truncated on turn {} for({}/{}); continuing",## add {} is session
                        iteration,
                        # spec.session_key or "default",
                        length_recovery_count,
                        _MAX_LENGTH_RECOVERIES,
                    )
                    # if hook.wants_streaming():
                    #     await hook.on_stream_end(context, resuming=True)
                    messages.append(build_assistant_message(
                        result,
                        reasoning_content=response.reasoning_content,
                        thinking_blocks=response.thinking_blocks,
                    ))
                    # messages.append(build_length_recovery_message())
                    # await hook.after_iteration(context)
                    continue

            assistant_message: dict[str, Any] | None = None
            if response.finish_reason != "error":
                assistant_message = build_assistant_message(
                    result,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

            messages.append(assistant_message or build_assistant_message(
                result,
                reasoning_content=response.reasoning_content,
                thinking_blocks=response.thinking_blocks,
            ))

            final_content = result
            context.final_content = final_content
            context.stop_reason = stop_reason
            break

        else:
            stop_reason = "max_iterations"
            if spec.max_iterations_message:
                final_content = spec.max_iterations_message.format(
                    max_iterations=spec.max_iterations,
                )
            else:
                # final_content = render_template(
                #     "agent/max_iterations_message.md",
                #     strip=True,
                #     max_iterations=spec.max_iterations,
                # )
                print("need to add max iteration msg")

            self._append_final_message(messages, final_content)


        return AgentRunResult(
            final_content=final_content,
            messages=messages,
            tools_used=tools_used,
            usage=usage,
            stop_reason=stop_reason,
            error=error,
            tool_events=tool_events,
            # had_injections=had_injections,
        )



    def _build_request_kwargs(
            self,
            spec: AgentRunSpec,
            messages: list[dict[str, Any]],
            *,
            tools: list[dict[str, Any]] | None,
        ) -> dict[str, Any]:

        kwargs: dict[str, Any] = {
            "messages": messages,
            "tools": tools,
            "model": spec.model,
        }
        if spec.temperature is not None:
            kwargs["temperature"] = spec.temperature
        if spec.max_tokens is not None:
            kwargs["max_tokens"] = spec.max_tokens
        if spec.reasoning_effort is not None:
            kwargs["reasoning_effort"] = spec.reasoning_effort
        return kwargs

    
    async def _request_model(
            self,
            spec: AgentRunSpec,
            messages: list[dict[str, Any]],
        ):
        wants_streaming = True
        timeout_s: float | None = spec.llm_timeout_s
        if timeout_s is None:
            # Default to a finite timeout to avoid per-session lock starvation when an LLM
            # request hangs indefinitely (e.g. gateway/network stall).
            # Set NANOBOT_LLM_TIMEOUT_S=0 to disable.
            raw = os.environ.get("NANOBOT_LLM_TIMEOUT_S", "300").strip()
            try:
                timeout_s = float(raw)
            except (TypeError, ValueError):
                timeout_s = 300.0
        if timeout_s is not None and timeout_s <= 0:
            timeout_s = None

        kwargs = self._build_request_kwargs(
            spec,
            messages,
            tools=spec.tools.get_definitions()
        )
        logger.info("Started Thinking by LLM")

        if wants_streaming:
            async def on_stream(delta: str) -> None:
                print(delta, end="")


            async def _stream(delta: str) -> None:
                await on_stream(delta)
        
            coro = self.provider.chat_stream(
                **kwargs,
                on_content_delta=_stream,
                # on_thinking_delta=_thinking,
            )
        else:
            coro = self.provider.chat(**kwargs)

        try:
            response = (
                await coro if timeout_s is None
                else await asyncio.wait_for(coro, timeout=timeout_s)
            )
        except asyncio.TimeoutError:
            return LLMResponse(
                content=f"Error calling LLM: timed out after {timeout_s:g}s",
                finish_reason="error",
                error_kind="timeout",
            )
        
        return response
    
    def _normalize_tool_result(
            self,
            spec: AgentRunSpec,
            tool_call_id: str,
            tool_name: str,
            result: Any
        ) -> Any:

        # _persist_tool_result should be implemented later

        if isinstance(result, str) and len(result) > spec.max_tool_result_chars:
            return truncate_text(result, spec.max_tool_result_chars)
        return result
        
    @staticmethod
    def _accumulate_usage(target: dict[str, int], addition: dict[str, int]) -> None:
        for key, value in addition.items():
            target[key] = target.get(key, 0) + value

    @staticmethod
    def _usage_dict(usage: dict[str, Any] | None) -> dict[str, int]:
        if not usage:
            return {}
        result: dict[str, int] = {}
        for key, value in usage.items():
            try:
                result[key] = int(value or 0)
            except (TypeError, ValueError):
                continue
        return result
    
    #later implement checkpointing
    async def _emit_checkpoint(
        self,
        spec: AgentRunSpec,
        payload: dict[str, Any],
    ) -> None:
        callback = spec.checkpoint_callback
        if callback is not None:
            await callback(payload)

    def _partition_tool_batches(
            self,
            spec: AgentRunSpec,
            tool_calls: list[ToolCallRequest],
    ):
        if not spec.concurrent_tools:
            return [[tc] for tc in tool_calls]
        
        batches: list[list[ToolCallRequest]] = []
        current_batch: list[ToolCallRequest] = []

        for tc in tool_calls:
            get_tool = getattr(spec.tools, "get", None)
            tool = get_tool(tc.name) if callable(get_tool) else None
            can_batch = bool(tool and tool.concurrency_safe)
            if can_batch:
                current_batch.append(tc)
                continue
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            batches.append([tc])
        if current_batch:
            batches.append(current_batch)
        return batches
    
    async def _run_tool(
            self,
            spec: AgentRunSpec,
            tool_call: ToolCallRequest,
    ) -> tuple[Any, dict[str, str], BaseException | None]:
        
        prepare_call = getattr(spec.tools, "prepare_call", None)
        tool, params, prep_error = None, tool_call.arguments, None
        if callable(prepare_call):
            with suppress(Exception):
                prepared = prepare_call(tool_call.name, tool_call.arguments)
                if isinstance(prepared, tuple) and len(prepared) == 3:
                    tool, params, prep_error = prepared
        try:
            if tool is not None:
                result = await tool.execute(**params)
            else:
                result = await spec.tools.execute(tool_call.name, params)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            event = {
                "name": tool_call.name,
                "status": "error",
                "detail": str(exc),
            }
            payload = f"Error: {type(exc).__name__}: {exc}"
            return payload, event, None
        
        detail = "" if result is None else str(result)
        detail = detail.replace("\n", " ").strip()
        if not detail:
            detail = "(empty)"
        elif len(detail) > 120:
            detail = detail[:120] + "..."
        return result, {"name": tool_call.name, "status": "ok", "detail": detail}, None
    
    async def _execute_tools(
            self,
            spec: AgentRunSpec,
            tool_calls: list[ToolCallRequest]
    ) -> tuple[list[Any], list[dict[str, str]], BaseException | None]:
        
        batches = self._partition_tool_batches(spec, tool_calls)
        tool_results: list[tuple[Any, dict[str, str], BaseException | None]] = []
        for batch in batches:
            if spec.concurrent_tools and len(batch) > 1:
                batch_results = await asyncio.gather(*(
                    self._run_tool(
                        spec, tool_call,
                    )
                    for tool_call in batch
                ))
                tool_results.extend(batch_results)
            else:
                batch_results = []
                for tool_call in batch:
                    result = await self._run_tool(
                        spec, tool_call,
                    )
                    tool_results.append(result)
                    batch_results.append(result)

        results: list[Any] = []
        events: list[dict[str, str]] = []
        fatal_error: BaseException | None = None
        for result, event, error in tool_results:
            results.append(result)
            events.append(event)
            if error is not None and fatal_error is None:
                fatal_error = error
        return results, events, fatal_error
    
    @staticmethod
    def _append_final_message(messages: list[dict[str, Any]], content: str | None) -> None:
        if not content:
            return
        if (
            messages
            and messages[-1].get("role") == "assistant"
            and not messages[-1].get("tool_calls")
        ):
            if messages[-1].get("content") == content:
                return
            messages[-1] = build_assistant_message(content)
            return
        messages.append(build_assistant_message(content))

