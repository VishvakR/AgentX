from typing import Any
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class RequestContext:
    """Per-request context for tools to inject at message processing."""
    channel: str
    chat_id: str
    message_id: str | None = None
    session_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

class ContextBuilder:

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md"]

    def __init__(
            self,
            workspace: Path,
    ):
        self.workspace = workspace

    def _load_bootstrap_files(self, workspace: Path | None = None) -> str:
        """Load all bootstrap files from workspace."""
        parts = []
        root = workspace or self.workspace
        root = Path(root).expanduser()
        if root is None:
            return ""

        for filename in self.BOOTSTRAP_FILES:
            file_path = root / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""
    
    def _build_system_prompt(
            self,
            workspace: Path | None = None
        ):

        root = workspace or self.workspace
        parts = []
        bootstrap_file = self._load_bootstrap_files(root)
        if(bootstrap_file):
            parts.append(bootstrap_file)

        #additional implementation
        return "\n\n".join(parts)

    def build_message(
            self,
            history,
            current_message: str,
            channel: str | None = None,
            chat_id: str | None = None,
            workspace: Path | None = None,
        ) -> list[dict[str, Any]]:


        user_content = self._build_user_content(current_message)
        if isinstance(user_content, str):
            merged = user_content
        
        messages = [
            {
                "role": "system",
                "content" : self._build_system_prompt(workspace),
            },
            *history
        ]

        if messages and messages[-1].get("role") == "user":
            messages[-1] = {
                **messages[-1],
                "content": (
                    str(messages[-1].get("content", ""))
                    + "\n\n"
                    + user_content
                ),
            }
        else:
            messages.append(
                {
                    "role": "user",
                    "content": user_content,
                }
            )

        return messages

    def _build_user_content(self, msg: str) -> str:
        return msg.strip() if msg else ""

