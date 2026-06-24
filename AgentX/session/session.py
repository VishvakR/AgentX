from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from dataclasses import dataclass, field


_STORABLE_ROLES = frozenset({"user", "assistant", "tool"})
_GROUP_START_ROLE = "assistant"


@dataclass
class Session:
    """In-memory representation of a single conversation session.

    Holds the message history, turn count, and arbitrary metadata.
    Designed to be serialised by :class:`SessionStore`.
    """

    session_key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    turn_count: int = 0

    # ── message helpers ──────────────────────────────────────────────

    def add_message(self, msg: dict[str, Any]) -> None:
        """Append a single message to history if it has a storable role."""
        if msg.get("role") not in _STORABLE_ROLES:
            return
        self.messages.append(msg)
        self._touch()

    def add_messages(self, msgs: list[dict[str, Any]]) -> None:
        """Append a batch of messages, filtering out system messages."""
        for msg in msgs:
            if msg.get("role") in _STORABLE_ROLES:
                self.messages.append(msg)
        self._touch()

    def complete_turn(self) -> None:
        """Mark a turn as completed (call after save)."""
        self.turn_count += 1
        self._touch()

    # ── history replay ───────────────────────────────────────────────

    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """Return the tail window of messages suitable for LLM replay.

        Preserves tool-call groups: if trimming would split an assistant
        message from its subsequent tool-result messages, the entire group
        is kept.

        System messages are never stored, so the returned list is ready
        to be spliced after a freshly-built system message.
        """
        if len(self.messages) <= max_messages:
            return list(self.messages)
        return self._trim_copy(max_messages)

    # ── trimming ─────────────────────────────────────────────────────

    def trim(self, max_messages: int = 50) -> int:
        """In-place trim to *at most* ``max_messages``, preserving groups.

        Returns the number of messages removed.
        """
        if len(self.messages) <= max_messages:
            return 0
        trimmed = self._trim_copy(max_messages)
        removed = len(self.messages) - len(trimmed)
        self.messages = trimmed
        self._touch()
        return removed

    def _trim_copy(self, max_messages: int) -> list[dict[str, Any]]:
        """Return a trimmed copy of messages preserving tool-call groups."""
        if len(self.messages) <= max_messages:
            return list(self.messages)

        candidate_start = len(self.messages) - max_messages
        for i in range(candidate_start, len(self.messages)):
            msg = self.messages[i]
            role = msg.get("role")
            if role == "user":
                return self.messages[i:]
            if role == _GROUP_START_ROLE and not msg.get("tool_calls"):
                return self.messages[i:]
            if role == _GROUP_START_ROLE and msg.get("tool_calls"):
                return self.messages[i:]
        return self.messages[candidate_start:]

    # ── reset / serialisation ────────────────────────────────────────

    def clear(self) -> None:
        """Reset messages and turn count, keep key and metadata."""
        self.messages.clear()
        self.turn_count = 0
        self._touch()

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON storage."""
        return {
            "session_key": self.session_key,
            "messages": self.messages,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": self.turn_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Deserialise from a plain dict."""
        return cls(
            session_key=data["session_key"],
            messages=data.get("messages", []),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            turn_count=data.get("turn_count", 0),
        )

    # ── internal ─────────────────────────────────────────────────────

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def __len__(self) -> int:
        return len(self.messages)

    def __repr__(self) -> str:
        return (
            f"Session(key={self.session_key!r}, "
            f"messages={len(self.messages)}, "
            f"turns={self.turn_count})"
        )
