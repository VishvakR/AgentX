"""Typer CLI for Agent Sara.

Commands:
    agent         Interactive chat (default) or single-message mode.
    agent -m "…"  Send one message and exit.
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Any, Optional

import typer
from loguru import logger
from rich.console import Console

from AgentX.providers import OpenaiCompactProvider, ProviderSpec
from AgentX.cli.banner import banner
from AgentX.tools.registry import ToolRegistry
from AgentX.tools.weather import WeatherTool
from AgentX.tools.web import WebSearchTool
from AgentX.agent.loop import AgentCoreLoop
from AgentX.bus import MessageBus, InboundMessage
from AgentX.utils.helpers import sync_workspace_templates
from AgentX.session import SessionStore
from AgentX.config.schema import AgentDefaults
from AgentX.cli.stream import StreamRenderer
from AgentX.config.schema import mcp_servers, MCPServerConfig
from AgentX.config.loader import load_mcp_servers

app = typer.Typer(
    name="sara",
    help="Agent Sara — AI assistant CLI",
    add_completion=False,
    no_args_is_help=False,
)

_console = Console()

# ── Exit keywords ────────────────────────────────────────────────────

_EXIT_COMMANDS = frozenset({"exit", "quit", "q", "/quit", "/exit"})

# ── Slash commands (interactive mode only) ───────────────────────────

_SLASH_COMMANDS: dict[str, str] = {
    "/new":      "Start a new session (clears context, new session key).",
    "/clear":    "Clear conversation history for this session.",
    "/history":  "Show message and turn count for the current session.",
    "/sessions": "List all saved sessions.",
    "/help":     "Show available commands.",
}


def _print_help() -> None:
    _console.print("\n  [bold]Commands:[/bold]")
    for cmd, desc in _SLASH_COMMANDS.items():
        _console.print(f"    [cyan]{cmd:12s}[/cyan] {desc}")
    _console.print(f"    [cyan]{'exit':12s}[/cyan] Exit the agent.")
    _console.print()


def _generate_session_key() -> str:
    """Generate a unique session key based on timestamp."""
    return f"cli:{int(time.time())}"


# ── Provider / tools setup ───────────────────────────────────────────

def _build_provider(defaults: AgentDefaults) -> OpenaiCompactProvider:
    spec = ProviderSpec(
        name="ollama",
        keywords=("ollama",),
        env_key="OLLAMA_API_KEY",
        display_name="Ollama",
        backend="openai_compat",
        is_local=True,
        detect_by_base_keyword="11434",
        default_api_base="http://localhost:11434/v1",
    )
    return OpenaiCompactProvider(
        default_model=defaults.model,
        api_key="ollama",
        base_url="http://localhost:11434/v1",
        spec=spec,
    )


def _build_tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(WeatherTool())
    registry.register(WebSearchTool())
    mcp_server = load_mcp_servers(mcp_servers)
    return registry, mcp_server


def _build_loop(
    defaults: AgentDefaults,
    bus: MessageBus,
    store: SessionStore,
) -> AgentCoreLoop:
    provider = _build_provider(defaults)
    loop = AgentCoreLoop(
        bus=bus,
        provider=provider,
        workspace=None,
        session_store=store,
        max_history_messages=defaults.max_history_messages,
    )
    return loop


# ── Single-message mode (bus-driven) ────────────────────────────────

async def _run_single_message(
    loop: AgentCoreLoop,
    bus: MessageBus,
    tools: ToolRegistry,
    mcp_servers: dict[str, MCPServerConfig],
    session_key: str,
    message: str,
    defaults: AgentDefaults,
) -> None:
    """Send one message via the bus, stream the response, and exit."""
    renderer = StreamRenderer(
        bot_name=defaults.bot_name or "Sara",
        bot_icon="🤖",
        render_markdown=True,
        show_spinner=True,
    )

    # Register tools and stream callbacks on the loop.
    loop.tools = tools
    loop._mcp_servers = mcp_servers
    loop.set_stream_callbacks(
        on_stream=renderer.on_delta,
        on_stream_end=renderer.on_end,
    )

    # Start the bus-driven loop as a background task.
    loop_task = asyncio.create_task(loop.run())
    await asyncio.sleep(0.05)  # Let it start consuming.

    try:
        # Publish the user message to the bus.
        await bus.publish_inbound(InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id="direct",
            content=message,
            session_key_override=session_key,
        ))

        # Wait for the outbound response from the bus.
        outbound = await asyncio.wait_for(
            bus.consume_outbound(), timeout=120,
        )

        # If nothing was streamed (non-streaming path), print final content.
        if not renderer.streamed and outbound.content:
            renderer.ensure_header()
            _console.print(outbound.content)

    except asyncio.TimeoutError:
        _console.print("\n  [red]Error:[/red] Timed out waiting for response.\n")
    finally:
        await renderer.close()
        loop.stop()
        await asyncio.wait_for(loop_task, timeout=5)

    _console.print()  # trailing newline


# ── Interactive mode (bus-driven) ────────────────────────────────────

_prompt_session = None

async def _get_user_input() -> str | None:
    """Read user input using prompt_toolkit for better editing support."""
    global _prompt_session
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML

        if _prompt_session is None:
            _prompt_session = PromptSession()
        text = await _prompt_session.prompt_async(HTML("<b>You: </b>"))
        return text.strip()

    except ImportError:
        return input("You: ").strip()


async def _run_interactive(
    loop: AgentCoreLoop,
    bus: MessageBus,
    tools: ToolRegistry,
    mcp_servers: dict[str, MCPServerConfig],
    store: SessionStore,
    session_key: str,
    defaults: AgentDefaults,
) -> None:
    """Interactive chat loop driven by the message bus.

    The AgentCoreLoop.run() is started as a background task. User messages
    are published to bus.inbound, and outbound responses are consumed from
    bus.outbound. Stream callbacks render LLM deltas to the terminal in
    real time.
    """
    bot_name = defaults.bot_name or "Sara"
    current_session_key = session_key

    # Create a mutable renderer reference — we'll swap it per turn.
    renderer: StreamRenderer | None = None

    async def _on_stream(delta: str) -> None:
        if renderer is not None:
            await renderer.on_delta(delta)

    async def _on_stream_end(*, resuming: bool = False) -> None:
        if renderer is not None:
            await renderer.on_end(resuming=resuming)

    # Register tools and stream callbacks on the loop.
    loop.tools = tools
    loop._mcp_servers = mcp_servers
    loop.set_stream_callbacks(
        on_stream=_on_stream,
        on_stream_end=_on_stream_end,
    )

    # Start the bus-driven loop as a background task.
    loop_task = asyncio.create_task(loop.run())
    await asyncio.sleep(0.05)  # Let it start consuming.

    # ── Welcome banner ───────────────────────────────────────────
    _print_session_banner(bot_name, defaults.model, current_session_key, store)

    # ── Main input loop ──────────────────────────────────────────
    try:
        while True:
            # Get user input.
            try:
                user_input = await _get_user_input()
            except (EOFError, KeyboardInterrupt):
                _console.print("\n[dim]Goodbye![/dim]")
                break

            if user_input is None or not user_input:
                continue

            # ── Exit commands ────────────────────────────────────
            if user_input.lower() in _EXIT_COMMANDS:
                _console.print("[dim]Goodbye![/dim]")
                break

            # ── Slash commands ───────────────────────────────────
            lower = user_input.lower()

            if lower == "/new":
                current_session_key = _generate_session_key()
                _console.print(
                    f"  [green]New session started:[/green] "
                    f"[dim]{current_session_key}[/dim]\n"
                )
                continue

            if lower == "/clear":
                store.delete(current_session_key)
                _console.print("  [green]Session cleared.[/green]\n")
                continue

            if lower == "/history":
                s = store.get_or_create(current_session_key)
                _console.print(
                    f"  {len(s.messages)} messages, {s.turn_count} turns\n"
                )
                continue

            if lower == "/sessions":
                keys = store.list_sessions()
                if keys:
                    _console.print("  [bold]Saved sessions:[/bold]")
                    for k in keys:
                        s = store.get_or_create(k)
                        marker = " [cyan]←[/cyan]" if k == current_session_key else ""
                        _console.print(f"    {k}  ({s.turn_count} turns){marker}")
                else:
                    _console.print("  [dim]No saved sessions.[/dim]")
                _console.print()
                continue

            if lower == "/help":
                _print_help()
                continue

            if lower.startswith("/"):
                _console.print(
                    f"  [yellow]Unknown command:[/yellow] {user_input}. "
                    "Type [cyan]/help[/cyan] for options.\n"
                )
                continue

            # ── Process message via the bus ──────────────────────
            renderer = StreamRenderer(
                bot_name=bot_name,
                bot_icon="🤖",
                render_markdown=True,
                show_spinner=True,
            )

            try:
                # Publish user message to the bus.
                await bus.publish_inbound(InboundMessage(
                    channel="cli",
                    sender_id="user",
                    chat_id="direct",
                    content=user_input,
                    session_key_override=current_session_key,
                ))

                # Wait for the outbound response.
                outbound = await asyncio.wait_for(
                    bus.consume_outbound(), timeout=120,
                )

                # If nothing was streamed, print the final content.
                if not renderer.streamed and outbound.content:
                    renderer.ensure_header()
                    _console.print(outbound.content)

            except asyncio.TimeoutError:
                _console.print("\n  [red]Error:[/red] Timed out waiting for response.\n")
            except Exception as exc:
                logger.exception("Error processing message")
                _console.print(f"\n  [red]Error:[/red] {exc}\n")
            finally:
                if renderer is not None:
                    await renderer.close()
                    renderer = None

            _console.print()  # spacing between turns

    finally:
        loop.stop()
        try:
            await asyncio.wait_for(loop_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            loop_task.cancel()


def _print_session_banner(
    bot_name: str,
    model: str,
    session_key: str,
    store: SessionStore,
) -> None:
    """Print the welcome / session info banner."""
    _console.print()
    _console.print(
        f"  [bold cyan]Agent {bot_name}[/bold cyan]  •  "
        f"model: [dim]{model}[/dim]"
    )
    _console.print(f"  Session: [dim]{session_key}[/dim]")

    existing = store.get_or_create(session_key)
    if existing.turn_count > 0:
        _console.print(
            f"  [dim]Resuming ({existing.turn_count} turns, "
            f"{len(existing.messages)} messages)[/dim]"
        )
    _console.print(
        "  Type [cyan]/help[/cyan] for commands, [cyan]exit[/cyan] to quit."
    )
    _console.print()


# ── Typer command ────────────────────────────────────────────────────

@app.command()
def agent(
    message: Optional[str] = typer.Option(
        None,
        "--message", "-m",
        help="Send a single message and exit (non-interactive mode).",
    ),
    session: str = typer.Option(
        "cli:direct",
        "--session", "-s",
        help="Session key for conversation history.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Override the default LLM model.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show debug logs.",
    ),
) -> None:
    """Chat with Agent Sara.

    Without --message: starts an interactive REPL.
    With --message "…": sends one message, prints the response, and exits.
    """
    # Configure loguru: suppress verbose output unless --verbose.
    _configure_logging(verbose)
    banner()

    defaults = AgentDefaults()
    if model:
        defaults.model = model

    sync_workspace_templates(defaults.workspace)
    bus = MessageBus()
    store = SessionStore(defaults.session_dir)
    tools, mcp_servers = _build_tools()
    loop = _build_loop(defaults, bus, store)

    if message:
        # Single-message mode.
        asyncio.run(
            _run_single_message(loop, bus, tools, mcp_servers, session, message, defaults)
        )
    else:
        # Interactive mode.
        asyncio.run(
            _run_interactive(loop, bus, tools, mcp_servers, store, session, defaults)
        )


def _configure_logging(verbose: bool) -> None:
    """Set loguru level based on --verbose flag."""
    import sys as _sys
    logger.remove()  # Remove default handler.
    if verbose:
        logger.add(_sys.stderr, level="DEBUG")
    else:
        logger.add(_sys.stderr, level="WARNING")

@app.command()
def version():
    print("1.0.0")


# ── Entry point for backward compatibility ───────────────────────────

def run_cli() -> None:
    """Entry point for ``python -m AgentX.main``."""
    app()
