from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str | None
    # tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"

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
    ) -> LLMResponse:
        pass