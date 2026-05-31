import os
import asyncio
from urllib.parse import urlparse
from typing import TYPE_CHECKING

from SaraAgent.providers import LLMProvider, LLMResponse, ProviderSpec

if TYPE_CHECKING:
    from openai import AsyncOpenAI as AsyncOpenAIType

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
        self.spec = spec

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

        if self.is_local:
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
