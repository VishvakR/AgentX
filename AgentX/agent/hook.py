from dataclasses import dataclass, field
from typing import Any

from AgentX.providers import LLMResponse, ToolCallRequest

@dataclass(slots=True)
class AgentHookContext:
    """Mutable per-iteration state exposed to runner hooks."""

    iteration: int
    messages: list[dict[str, Any]]
    response: LLMResponse | None = None
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    tool_events: list[dict[str, str]] = field(default_factory=list)
    streamed_content: bool = False
    streamed_reasoning: bool = False
    final_content: str | None = None
    stop_reason: str | None = None
    error: str | None = None