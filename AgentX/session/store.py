"""File-based session persistence using JSON."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from loguru import logger

from AgentX.session.session import Session


def _key_to_filename(session_key: str) -> str:
    """Convert a session key to a safe filename.

    Uses the raw key if it's filesystem-safe, otherwise falls back to
    a SHA-256 hash prefix.  The ``.json`` extension is always appended.
    """
    safe = session_key.replace(":", "_").replace("/", "_")
    # Guard against overly long or exotic keys.
    if len(safe) > 100 or not all(c.isalnum() or c in "_-." for c in safe):
        safe = hashlib.sha256(session_key.encode()).hexdigest()[:16]
    return f"{safe}.json"


class SessionStore:
    """Load and persist sessions as individual JSON files.

    Each session is stored as ``<storage_dir>/<filename>.json`` where
    *filename* is derived from the session key.  An in-memory cache
    avoids redundant disk reads within a single process lifetime.
    """

    def __init__(self, storage_dir: str | Path) -> None:
        self._dir = Path(storage_dir).expanduser().resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}
        logger.debug("SessionStore initialised at {}", self._dir)

    # ── public API ───────────────────────────────────────────────────

    def get_or_create(self, session_key: str) -> Session:
        """Return an existing session or create a new one."""
        if session_key in self._cache:
            return self._cache[session_key]

        path = self._path_for(session_key)
        if path.exists():
            session = self._load(path, session_key)
            logger.info(
                "Loaded session {!r} ({} messages, {} turns)",
                session_key,
                len(session.messages),
                session.turn_count,
            )
        else:
            session = Session(session_key=session_key)
            logger.info("Created new session {!r}", session_key)

        self._cache[session_key] = session
        return session

    def save(self, session: Session) -> None:
        """Persist a session to disk."""
        path = self._path_for(session.session_key)
        data = session.to_dict()
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(path)
        except OSError:
            logger.exception("Failed to save session {!r}", session.session_key)
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
        self._cache[session.session_key] = session
        logger.debug(
            "Saved session {!r} ({} messages)",
            session.session_key,
            len(session.messages),
        )

    def delete(self, session_key: str) -> bool:
        """Delete a session from disk and cache.  Returns True if it existed."""
        self._cache.pop(session_key, None)
        path = self._path_for(session_key)
        if path.exists():
            path.unlink()
            logger.info("Deleted session {!r}", session_key)
            return True
        return False

    def list_sessions(self) -> list[str]:
        """List all session keys that have persisted files.

        Note: only returns keys that can be reverse-mapped.  Hash-based
        filenames cannot be reversed, so we read the ``session_key``
        field from inside each file.
        """
        keys: list[str] = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                key = data.get("session_key")
                if key:
                    keys.append(key)
            except (json.JSONDecodeError, OSError):
                logger.warning("Skipping corrupt session file {}", path.name)
        return keys

    def has(self, session_key: str) -> bool:
        """Check whether a session exists (in cache or on disk)."""
        if session_key in self._cache:
            return True
        return self._path_for(session_key).exists()

    # ── internal ─────────────────────────────────────────────────────

    def _path_for(self, session_key: str) -> Path:
        return self._dir / _key_to_filename(session_key)

    def _load(self, path: Path, session_key: str) -> Session:
        """Load a session from a JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            session = Session.from_dict(data)
            # Ensure the key matches (in case of hash collision or rename).
            if session.session_key != session_key:
                logger.warning(
                    "Session key mismatch: file has {!r} but requested {!r}",
                    session.session_key,
                    session_key,
                )
                session.session_key = session_key
            return session
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "Corrupt session file {} — starting fresh: {}",
                path.name,
                exc,
            )
            return Session(session_key=session_key)

    def __repr__(self) -> str:
        return f"SessionStore(dir={self._dir}, cached={len(self._cache)})"
