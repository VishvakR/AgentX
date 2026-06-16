from __future__ import annotations
import asyncio
import time
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from dataclasses import dataclass, field
from loguru import logger

from AgentX.bus import InboundMessage, MessageBus, OutboundMessage
from AgentX.providers import LLMProvider
from AgentX.config.schema import AgentDefaults
from AgentX.agent.runner import AgentRunner, AgentRunSpec
from AgentX.tools.context import RequestContext, ContextBuilder
from AgentX.tools.registry import ToolRegistry

class RunState(Enum):
    # RESTORE = auto()
    # COMPACT = auto()
    # COMMAND = auto()
    BUILD = auto()
    RUN = auto()
    # SAVE = auto()
    # RESPOND = auto()
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
    session: str | None = None #Session

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
    # (RunState.RESTORE, "ok"): RunState.COMPACT,
    # (RunState.COMPACT, "ok"): RunState.COMMAND,
    # (RunState.COMMAND, "dispatch"): RunState.BUILD,
    # (RunState.COMMAND, "shortcut"): RunState.DONE,
    (RunState.BUILD, "ok"): RunState.RUN,
    (RunState.RUN, "ok"): RunState.DONE, #SAVE
    # (RunState.SAVE, "ok"): RunState.RESPOND,
    # (RunState.RESPOND, "ok"): RunState.DONE,
    }
    def __init__(
            self,
            bus: MessageBus,
            provider: LLMProvider,
            workspace: Path,
            model: str | None = None,
            max_iterations: int | None = None,
            max_tool_result_chars: int | None = None

        ):
        defaults = AgentDefaults()
        self.bus = bus
        self.context = ContextBuilder(workspace=None)
        self.runner = AgentRunner(provider)
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = (
            max_iterations if max_iterations is not None else defaults.max_tool_iterations
        )
        self.max_tool_result_chars = (
            max_tool_result_chars
            if max_tool_result_chars is not None
            else defaults.max_tool_result_chars
        )
        self.tools = ToolRegistry()
    
    @classmethod
    def fromConfig(
            cls,
            config: Any,
            bus: MessageBus | None = None,
            **extra: Any,
        ) -> AgentCoreLoop:
        
        pass
        

    def _build_initial_message(
            self,
            msg: InboundMessage,
            #session: Session
            history: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:

        return self.context.build_message(history, msg.content, msg.channel, msg.chat_id)


    async def _run_agent_loop(
            self,
            initial_message: list[dict],
            on_progress: Callable[..., Awaitable[None]] | None = None,
            on_stream: Callable[[str], Awaitable[None]] | None = None,
            on_stream_end: Callable[..., Awaitable[None]] | None = None,
            on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
            *,
            # session: Session | None = None,
            channel: str = "cli",
            chat_id: str = "direct",
            message_id: str | None = None,
            metadata: dict[str, Any] | None = None,
            session_key: str | None = None,
            tools: ToolRegistry | None = None,
        ) ->  tuple[str | None, list[str], list[dict], str, bool]:

            try:
                result = await self.runner.run(
                    AgentRunSpec(
                        initial_messages=initial_message,
                        tools=tools or self.tools,
                        model=self.model,
                        max_iterations=self.max_iterations,
                        max_tool_result_chars=self.max_tool_result_chars,
                    )
                )
            finally:
                print("Done")
            
            print(result)

    async def run():
        pass

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

        key = session_key #or msg.session_key
        t = time.time()

        ctx = RunContext(
            msg=msg,
            session=None,
            session_key=key,
            state=RunState.BUILD,
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


        

    async def _state_build(self, ctx: RunContext):
        ctx.initial_messages = self._build_initial_message(
            msg=ctx.msg,
            history=ctx.history,
            #need to implement further
        )
        return "ok"
    
    async def _state_run(self, ctx: RunContext):
        result = await self._run_agent_loop(
            ctx.initial_messages,
            on_progress=ctx.on_progress,
            on_stream=ctx.on_stream,
            on_stream_end=ctx.on_stream_end,
            on_retry_wait=ctx.on_retry_wait,
            # session=ctx.session,
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            # message_id=ctx.msg.metadata.get("message_id"),
            metadata=ctx.msg.metadata,
            # session_key=ctx.session_key,
            tools=ctx.tools,
        )

        # final_content, tools_used, all_msgs, stop_reason, had_injections = result
        # ctx.final_content = final_content
        # ctx.tools_used = tools_used
        # ctx.all_messages = all_msgs
        # ctx.stop_reason = stop_reason
        # ctx.had_injections = had_injections
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

        msg = InboundMessage(
            channel=channel, sender_id="user", chat_id=chat_id,
            content=content, media=media or [], metadata=metadata,
        )
        # Share the dispatch lock so direct calls serialize with bus turns.
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        try:
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
        finally:
            print("done")




        




