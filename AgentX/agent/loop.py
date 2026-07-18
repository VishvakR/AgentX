from __future__ import annotations
import asyncio
import time
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from dataclasses import dataclass, field
from loguru import logger
from contextlib import AsyncExitStack

from AgentX.bus import InboundMessage, MessageBus, OutboundMessage
from AgentX.providers import LLMProvider
from AgentX.config.schema import AgentDefaults
from AgentX.agent.runner import AgentRunner, AgentRunSpec
from AgentX.agent.context import RequestContext, ContextBuilder
from AgentX.tools.registry import ToolRegistry
from AgentX.session import Session, SessionStore

class RunState(Enum):
    RESTORE = auto()
    # COMPACT = auto()
    # COMMAND = auto()
    BUILD = auto()
    RUN = auto()
    SAVE = auto()
    RESPOND = auto()
    DONE = auto()

@dataclass
class StateTraceEntry:
    state: RunState
    started_at: float
    duration_ms: float
    event: str
    error: str | None = None



@dataclass
class RunContext:
    msg: InboundMessage
    session_key: str
    state: RunState
    turn_id: str
    session: Session | None = None

    history: list[dict[str, Any]] = field(default_factory=list)
    initial_messages: list[dict[str, Any]] = field(default_factory=list)

    final_content: str | None = None
    tools_used: list[str] = field(default_factory=list)
    all_messages: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    had_injections: bool = False
    outbound: OutboundMessage | None = None

    on_progress: Callable[..., Awaitable[None]] | None = None
    on_stream: Callable[[str], Awaitable[None]] | None = None
    on_stream_end: Callable[..., Awaitable[None]] | None = None
    on_retry_wait: Callable[[str], Awaitable[None]] | None = None

    tools: ToolRegistry | None = None
    trace: list[StateTraceEntry] = field(default_factory=list)


class AgentCoreLoop:

    _TRANSITIONS: dict[tuple[RunState, str], RunState] = {
        (RunState.RESTORE, "ok"): RunState.BUILD,
        (RunState.BUILD, "ok"): RunState.RUN,
        (RunState.RUN, "ok"): RunState.SAVE,
        (RunState.SAVE, "ok"): RunState.RESPOND,
        (RunState.RESPOND, "ok"): RunState.DONE,
    }

    def __init__(
            self,
            bus: MessageBus,
            provider: LLMProvider,
            workspace: Path | None = None,
            model: str | None = None,
            max_iterations: int | None = None,
            max_tool_result_chars: int | None = None,
            mcp_servers: dict | None = None,
            session_store: SessionStore | None = None,
            max_history_messages: int | None = None,
        ):
        defaults = AgentDefaults()
        self.bus = bus
        self.context = ContextBuilder(workspace=workspace)
        self.runner = AgentRunner(provider)
        self.provider = provider
        self.workspace = workspace or defaults.workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = (
            max_iterations if max_iterations is not None else defaults.max_tool_iterations
        )
        self.max_tool_result_chars = (
            max_tool_result_chars
            if max_tool_result_chars is not None
            else defaults.max_tool_result_chars
        )
        self.max_history_messages = (
            max_history_messages
            if max_history_messages is not None
            else defaults.max_history_messages
        )
        self.tools = ToolRegistry()
        self._mcp_servers = mcp_servers or {}
        self._mcp_stacks: dict[str, AsyncExitStack] = {}
        self._mcp_connected = False
        self._mcp_connecting = False
        self._session_locks: dict[str, asyncio.Lock] = {}

        # Stream callbacks — set via set_stream_callbacks() for bus-driven mode.
        self._on_stream: Callable[[str], Awaitable[None]] | None = None
        self._on_stream_end: Callable[..., Awaitable[None]] | None = None

        # Session store — create a default one if none is provided.
        if session_store is not None:
            self.session_store = session_store
        else:
            self.session_store = SessionStore(defaults.session_dir)
    
    @classmethod
    def fromConfig(
            cls,
            config: Any,
            bus: MessageBus | None = None,
            **extra: Any,
        ) -> AgentCoreLoop:
        
        pass

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers"""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from AgentX.mcp.client import connect_mcp_servers
        try:
            self._mcp_stacks = await connect_mcp_servers(self._mcp_servers, self.tools)
            if self._mcp_stacks:
                self._mcp_connected = True
            else:
                logger.warning("No MCP servers connected successfully (will retry next message)")
        except asyncio.CancelledError:
            logger.warning("MCP connection cancelled (will retry next message)")
            self._mcp_stacks.clear()
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            self._mcp_stacks.clear()
        finally:
            self._mcp_connecting = False
        

    def _build_initial_message(
            self,
            msg: InboundMessage,
            history: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:

        return self.context.build_message(history, msg.content, msg.channel, msg.chat_id, workspace=self.workspace)


    async def _run_agent_loop(
            self,
            initial_message: list[dict],
            on_progress: Callable[..., Awaitable[None]] | None = None,
            on_stream: Callable[[str], Awaitable[None]] | None = None,
            on_stream_end: Callable[..., Awaitable[None]] | None = None,
            on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
            *,
            channel: str = "cli",
            chat_id: str = "direct",
            message_id: str | None = None,
            metadata: dict[str, Any] | None = None,
            session_key: str | None = None,
            tools: ToolRegistry | None = None,
        ):

            try:
                result = await self.runner.run(
                    AgentRunSpec(
                        initial_messages=initial_message,
                        tools=tools or self.tools,
                        model=self.model,
                        max_iterations=self.max_iterations,
                        max_tool_result_chars=self.max_tool_result_chars,
                        on_stream=on_stream,
                        on_stream_end=on_stream_end,
                    )
                )
            finally:
                logger.debug("Agent runner completed")
            
            return result

    async def run(self) -> None:
        """Main bus-driven event loop.

        Continuously consumes inbound messages from ``self.bus``, dispatches
        each through the state-machine pipeline (RESTORE → BUILD → RUN →
        SAVE → RESPOND → DONE), and publishes any outbound response back
        to the bus.

        The loop runs until :meth:`stop` is called or the task is cancelled.
        A single bad message never crashes the whole agent — errors are logged
        and the loop moves on to the next message.
        """
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started — waiting for inbound messages")

        try:
            while self._running:
                try:
                    # Block until the next inbound message arrives.
                    # Use wait_for so we can check _running periodically.
                    try:
                        msg = await asyncio.wait_for(
                            self.bus.consume_inbound(), timeout=1.0,
                        )
                    except asyncio.TimeoutError:
                        # No message within the poll interval — check _running.
                        continue

                    await self._dispatch_inbound(msg)

                except asyncio.CancelledError:
                    logger.info("Agent loop cancelled")
                    raise
                except Exception:
                    # Isolate errors so one bad message doesn't kill the loop.
                    logger.exception("Unhandled error in agent loop iteration")

        except asyncio.CancelledError:
            pass
        finally:
            await self._cleanup_mcp()
            self._running = False
            logger.info("Agent loop stopped")

    def stop(self) -> None:
        """Signal the bus-driven loop to stop after the current message."""
        self._running = False
        logger.info("Agent loop stop requested")

    async def _cleanup_mcp(self) -> None:
        """Close all MCP server connections and subprocesses."""
        if not self._mcp_stacks:
            return
        for name, stack in list(self._mcp_stacks.items()):
            try:
                await stack.aclose()
                logger.debug("Closed MCP server '{}'", name)
            except RuntimeError as e:
                # Known MCP SDK issue: anyio cancel scope conflict during cleanup.
                # The server process is already terminated; this is benign.
                if "cancel scope" in str(e):
                    logger.debug("MCP server '{}' closed (anyio scope warning suppressed)", name)
                else:
                    logger.exception("Error closing MCP server '{}'", name)
            except Exception:
                logger.exception("Error closing MCP server '{}'", name)
        self._mcp_stacks.clear()
        self._mcp_connected = False

    @property
    def running(self) -> bool:
        """Whether the bus-driven loop is currently active."""
        return getattr(self, "_running", False)

    def set_stream_callbacks(
        self,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        """Register stream callbacks for bus-driven mode.

        When set, :meth:`_dispatch_inbound` will pass these to
        :meth:`_process_message` so LLM deltas are forwarded to the CLI
        renderer instead of being silently consumed.
        """
        self._on_stream = on_stream
        self._on_stream_end = on_stream_end

    async def _dispatch_inbound(self, msg: InboundMessage) -> None:
        """Route a single inbound message through the full pipeline.

        Resolves the session key, acquires the per-session lock, processes
        the message, and publishes the outbound response to the bus.
        """
        session_key = msg.session_id
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())

        async with lock:
            try:
                outbound = await self._process_message(
                    msg,
                    session_key=session_key,
                    tools=self.tools,
                    on_stream=self._on_stream,
                    on_stream_end=self._on_stream_end,
                )
                if outbound is not None:
                    await self.bus.publish_outbound(outbound)
                    logger.debug(
                        "Published outbound for session {!r} ({} chars)",
                        session_key,
                        len(outbound.content),
                    )
            except Exception as exc:
                logger.exception(
                    "Error processing message for session {!r}", session_key,
                )
                # Publish an error response so the CLI consumer unblocks
                # instead of hanging on bus.consume_outbound().
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=f"Error processing message: {exc}",
                    metadata={"error": True},
                ))

    async def _process_message(
            self,
            msg: InboundMessage,
            session_key: str | None = None,
            on_progress: Callable[..., Awaitable[None]] | None = None,
            on_stream: Callable[[str], Awaitable[None]] | None = None,
            on_stream_end: Callable[..., Awaitable[None]] | None = None,
            pending_queue: asyncio.Queue | None = None,
            ephemeral: bool = False,
            tools: ToolRegistry | None = None,
        ):

        key = session_key or msg.session_id
        t = time.time()

        ctx = RunContext(
            msg=msg,
            session=None,
            session_key=key,
            state=RunState.RESTORE,
            turn_id=f"{key}:{time.time_ns()}",

            on_progress=on_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,

            tools=tools,
        )

        while ctx.state is not RunState.DONE:
            handler_name = f"_state_{ctx.state.name.lower()}"
            handler = getattr(self, handler_name, None)
            if handler is None:
                raise RuntimeError(f"Missing state handler for {ctx.state}")
            
            t0 = time.perf_counter()
            try:
                event = await handler(ctx)
            except Exception:
                duration = (time.perf_counter() - t0) * 1000
                ctx.trace.append(
                    StateTraceEntry(
                        state=ctx.state,
                        started_at=t0,
                        duration_ms=duration,
                        event="",
                        error="exception",
                    )
                )
                raise

            duration = (time.perf_counter() - t0) * 1000
            ctx.trace.append(
                StateTraceEntry(
                    state=ctx.state,
                    started_at=t0,
                    duration_ms=duration,
                    event=event,
                )
            )
            logger.debug(
                "[turn {}] State {} took {:.1f}ms -> event {}",
                ctx.turn_id,
                ctx.state.name,
                duration,
                event,
            )

            next_state = self._TRANSITIONS.get((ctx.state, event))
            if next_state is None:
                raise RuntimeError(
                    f"[turn {ctx.turn_id}] No transition from {ctx.state} "
                    f"on event {event!r}"
                )
            ctx.state = next_state

        logger.debug(
            "[turn {}] Turn completed after {} states",
            ctx.turn_id,
            len(ctx.trace),
        )
        return ctx.outbound


    # ── State Handlers ───────────────────────────────────────────────

    async def _state_restore(self, ctx: RunContext) -> str:
        """Load session and populate ctx.history for the BUILD state."""
        session = self.session_store.get_or_create(ctx.session_key)
        ctx.session = session
        ctx.history = session.get_history(self.max_history_messages)
        logger.debug(
            "[turn {}] Restored {} history messages from session {!r}",
            ctx.turn_id,
            len(ctx.history),
            ctx.session_key,
        )
        return "ok"

    async def _state_build(self, ctx: RunContext) -> str:
        """Build the initial message list for the LLM."""
        ctx.initial_messages = self._build_initial_message(
            msg=ctx.msg,
            history=ctx.history,
        )
        return "ok"
    
    async def _state_run(self, ctx: RunContext) -> str:
        """Execute the agent runner."""
        result = await self._run_agent_loop(
            ctx.initial_messages,
            on_progress=ctx.on_progress,
            on_stream=ctx.on_stream,
            on_stream_end=ctx.on_stream_end,
            on_retry_wait=ctx.on_retry_wait,
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            metadata=ctx.msg.metadata,
            session_key=ctx.session_key,
            tools=ctx.tools,
        )

        if result is not None:
            ctx.final_content = result.final_content
            ctx.tools_used = result.tools_used
            ctx.all_messages = result.messages
            ctx.stop_reason = result.stop_reason
        return "ok"

    async def _state_save(self, ctx: RunContext) -> str:
        """Persist new messages from this turn into the session."""
        if ctx.session is None:
            return "ok"

        history_len = len(ctx.history)
        # initial_messages = system + history + user_message
        # The runner starts from initial_messages and appends.
        # new messages = all_messages[len(initial_messages):]
        initial_count = len(ctx.initial_messages)
        new_messages = ctx.all_messages[initial_count:]

        # Also store the user message from this turn.
        # Find the user message in initial_messages (the last one).
        user_msg = None
        for msg in reversed(ctx.initial_messages):
            if msg.get("role") == "user":
                user_msg = msg
                break

        if user_msg:
            ctx.session.add_message(user_msg)

        # Add all new messages from the runner (assistant replies, tool calls, tool results).
        if new_messages:
            ctx.session.add_messages(new_messages)

        ctx.session.complete_turn()

        # Trim if needed.
        ctx.session.trim(self.max_history_messages)

        # Persist.
        self.session_store.save(ctx.session)
        logger.debug(
            "[turn {}] Saved session {!r} ({} messages, turn {})",
            ctx.turn_id,
            ctx.session_key,
            len(ctx.session.messages),
            ctx.session.turn_count,
        )
        return "ok"

    async def _state_respond(self, ctx: RunContext) -> str:
        """Build the outbound response message."""
        if ctx.final_content:
            ctx.outbound = OutboundMessage(
                channel=ctx.msg.channel,
                chat_id=ctx.msg.chat_id,
                content=ctx.final_content,
                reply_to=ctx.msg.metadata.get("message_id"),
                metadata={
                    "tools_used": ctx.tools_used,
                    "stop_reason": ctx.stop_reason,
                    "turn": ctx.session.turn_count if ctx.session else 0,
                },
            )
        return "ok"
    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        media: list[str] | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        tools: ToolRegistry | None = None,
    ) -> OutboundMessage | None:
        """Process a message directly and return the outbound payload."""
        metadata: dict[str, Any] = {}
        await self._connect_mcp()

        msg = InboundMessage(
            channel=channel, sender_id="user", chat_id=chat_id,
            content=content, media=media or [], metadata=metadata,
        )
        # Share the dispatch lock so direct calls serialize with bus turns.
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            kwargs: dict[str, Any] = {
                "session_key": session_key,
                "on_progress": on_progress,
                "on_stream": on_stream,
                "on_stream_end": on_stream_end,
            }
            if tools is not None:
                kwargs["tools"] = tools
            return await self._process_message(
                msg,
                **kwargs,
            )
