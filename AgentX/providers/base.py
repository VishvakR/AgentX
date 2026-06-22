from abc import ABC, abstractmethod
from typing import Any
import json
from dataclasses import dataclass, field

@dataclass
class ToolCallRequest:
    """A tool call request from the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]
    extra_content: dict[str, Any] | None = None
    provider_specific_fields: dict[str, Any] | None = None
    function_provider_specific_fields: dict[str, Any] | None = None

    def to_openai_tool_call(self) -> dict[str, Any]:
        """Serialize to an OpenAI-style tool_call payload."""
        tool_call = {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }
        if self.extra_content:
            tool_call["extra_content"] = self.extra_content
        if self.provider_specific_fields:
            tool_call["provider_specific_fields"] = self.provider_specific_fields
        if self.function_provider_specific_fields:
            tool_call["function"]["provider_specific_fields"] = self.function_provider_specific_fields
        return tool_call

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict) # not yet implemented
    reasoning_content: str | None = None
    thinking_blocks: list[dict] | None = None
    error_kind: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0

    @property
    def should_execute_tools(self) -> bool:
        """Tools execute only when has_tool_calls AND finish_reason is a tool-capable stop.
        Blocks gateway-injected calls under ``refusal`` / ``content_filter`` / ``error`` (#3220)."""
        if not self.has_tool_calls:
            return False
        return self.finish_reason in ("tool_calls", "function_call", "stop")
    

class LLMProvider(ABC):
    def __init__(self, api_key: str | None = None, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def chat(
        self, 
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """Get the default model for this provider."""
        pass