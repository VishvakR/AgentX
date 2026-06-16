"""Message definitions for AgentSara Bus"""

from typing import Any
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class InboundMessage:
    """Represents an incoming message to the agent."""

    channel: str    # telegram, discord, slack, whatsapp, cli, etc.
    chat_id: str    # Unique identifier for the chat or conversation
    sender_id: str  # User identifier
    content: str    # Message content
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    session_key_override: str | None = None # Optional override for session key

    @property
    def session_id(self) -> str:
        """Unique key for session identification."""
        return self.session_key_override or f"{self.channel}:{self.chat_id}"
    
@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""

    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
