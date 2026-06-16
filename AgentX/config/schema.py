"""Configuration schema using Pydantic."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AgentDefaults(Base):
    workspace: str = "~/.AgentX/workspace"
    provider: str = ("auto")
    model: str = "qwen3.5:4b-mlx"
    max_tool_iterations: int = 200
    max_tool_result_chars: int = 16_000
    bot_name: str = "nanobot"  # Display name shown in CLI prompts (e.g. "{name} is thinking...")
    bot_icon: str = ""

class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)

class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str | None = Field(default=None, repr=False)
    api_base: str | None = None
    api_type: Literal["auto", "chat_completions", "responses"] = "auto"  # Request API surface
    extra_headers: dict[str, str] | None = None  # Custom headers (e.g. APP-Code for AiHubMix)
    extra_body: dict[str, Any] | None = None  # Extra provider request fields; shape depends on provider/API surface
    extra_query: dict[str, str] | None = None  # Extra query params (e.g. api-version for Azure-style gateways)
