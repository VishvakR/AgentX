<h1 align="center">AgentX</h1>

<p align="center">
  <strong>A modular, production-ready AI agent framework for building autonomous assistants with tool use, streaming, and persistent memory.</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#quickstart">Quickstart</a> •
  <a href="#usage">Usage</a> •
  <a href="#project-structure">Structure</a> •
  <a href="#extending">Extending</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#license">License</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.13+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.13+" />
  <img src="https://img.shields.io/badge/async-first-4B8BBE?style=flat-square" alt="Async First" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License" />
  <img src="https://img.shields.io/badge/status-alpha-orange?style=flat-square" alt="Alpha" />
</p>

---

## Overview

**AgentX** is an extensible Python framework for building autonomous AI agents that can reason, use tools, maintain conversation history, and stream responses in real time. Built with a clean bus-driven architecture, it decouples message transport from agent logic — making it easy to plug into CLIs, APIs, messaging platforms, or custom interfaces.

```
User → MessageBus → AgentCoreLoop (state machine) → LLM Provider → Tools → Response
```

> **"The agent that works FOR you."**

---

## Features

| Category | Details |
|----------|---------|
| **🧠 Agent Core** | State-machine loop (RESTORE → BUILD → RUN → SAVE → RESPOND) with configurable transitions |
| **🔧 Tool System** | JSON Schema–validated tools with input coercion, concurrent execution, and batched dispatch |
| **🔌 Provider Layer** | OpenAI-compatible provider with streaming support; extensible `LLMProvider` ABC for any backend |
| **💬 Session Persistence** | JSON-backed session store with turn tracking, history trimming, and tool-call group preservation |
| **📨 Message Bus** | Async inbound/outbound queues decouple channels (CLI, API, bots) from agent logic |
| **🖥️ Rich CLI** | Interactive REPL with live markdown rendering, thinking spinner, slash commands, and session management |
| **⚡ Streaming** | Real-time token streaming from LLM to terminal via Rich Live with callback-driven architecture |
| **🏗️ Persona Templates** | SOUL.md, AGENT.md, USER.md templates define the agent's personality and system context |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / API / Bot                       │
│                     (InboundMessage producer)                │
└──────────────────────────┬──────────────────────────────────┘
                           │ publish_inbound()
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                       MessageBus                             │
│               inbound: asyncio.Queue                         │
│               outbound: asyncio.Queue                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ consume_inbound()
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    AgentCoreLoop.run()                       │
│                                                              │
│  ┌─────────┐   ┌───────┐   ┌─────┐   ┌──────┐   ┌─────────┐  │
│  │ RESTORE │──▶│ BUILD │──▶│ RUN │──▶│ SAVE │──▶│ RESPOND │  │
│  │(session)│   │ (ctx) │   │(LLM)│   │(disk)│   │  (out)  │  │
│  └─────────┘   └───────┘   └─────┘   └──────┘   └─────────┘  │
│                               │                              │
│                     ┌─────────┴──────────┐                   │
│                     ▼                    ▼                   │
│              AgentRunner          ToolRegistry               │
│           (iteration loop)     (execute + validate)          │
│                     │                                        │
│                     ▼                                        │
│              LLMProvider                                     │
│         (chat / chat_stream)                                 │
└──────────────────────────────────────────────────────────────┘
                           │ publish_outbound()
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  CLI / API / Bot                             │
│               (OutboundMessage consumer)                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Quickstart

### Prerequisites

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- A running LLM backend (e.g., [Ollama](https://ollama.ai) for local models)

### Installation

```bash
# Clone the repository
git clone https://github.com/VishvakR/AgentX.git
cd AgentX

# Install dependencies with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Run

```bash
# Interactive mode (REPL)
uv run python -m AgentX.main agent

# Single-message mode
uv run python -m AgentX.main agent -m "What is the capital of France?"

# With custom session and model
uv run python -m AgentX.main agent -m "Hello" -s my:session --model llama3:8b

# Enable debug logging
uv run python -m AgentX.main agent -v
```

---

## Usage

### Interactive Mode

```
╭──────────────────────────────────────────────────╮
│  █████╗  ██████╗ ███████╗███╗   ██╗████████╗██╗  ██╗  │
│ ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝╚██╗██╔╝  │
│ ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║    ╚███╔╝   │
│ ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║    ██╔██╗   │
│ ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ██╔╝ ██╗  │
│ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝  │
│                                                          │
│             The Agent that Works FOR You                 │
╰──────────────────────────────────────────────────╯

  Agent Sara  •  model: qwen3.5:4b-mlx
  Session: cli:direct
  Type /help for commands, exit to quit.

You: What is 7 times 8?

🤖 Sara
╭─ Sara ─────────────────────────────────────────╮
│ 7 times 8 is **56**.                            │
╰─────────────────────────────────────────────────╯
```

### Slash Commands

| Command | Description |
|---------|-------------|
| `/new` | Start a new session with an auto-generated key |
| `/clear` | Clear conversation history for the current session |
| `/history` | Show message and turn count |
| `/sessions` | List all saved sessions |
| `/help` | Show available commands |
| `exit` / `quit` / `q` | Exit the agent |

### CLI Options

```
Usage: python -m AgentX.main agent [OPTIONS]

Options:
  -m, --message TEXT   Send a single message and exit
  -s, --session TEXT   Session key (default: cli:direct)
  --model TEXT         Override the default LLM model
  -v, --verbose        Show debug logs
  --help               Show this message and exit
```

---

## Project Structure

```
Agentx/
├── AgentX/                         # Main package
│   ├── __init__.py
│   ├── main.py                     # Entry point
│   │
│   ├── agent/                      # Core agent logic
│   │   ├── loop.py                 # AgentCoreLoop — state machine + bus-driven event loop
│   │   ├── runner.py               # AgentRunner — LLM iteration loop with tool execution
│   │   ├── context.py              # ContextBuilder — system prompt + message assembly
│   │   └── hook.py                 # Hook context for lifecycle events
│   │
│   ├── bus/                        # Message bus
│   │   ├── bus.py                  # MessageBus — async inbound/outbound queues
│   │   └── messages.py             # InboundMessage / OutboundMessage dataclasses
│   │
│   ├── cli/                        # Command-line interface
│   │   ├── command.py              # Typer CLI — interactive REPL + single-message mode
│   │   ├── stream.py               # StreamRenderer — Rich Live markdown streaming
│   │   └── banner.py               # ASCII art banner
│   │
│   ├── providers/                  # LLM provider abstraction
│   │   ├── base.py                 # LLMProvider ABC, LLMResponse, ToolCallRequest
│   │   ├── openai_compat_provider.py  # OpenAI-compatible provider (Ollama, OpenAI, etc.)
│   │   └── registry.py             # Provider auto-detection and registry
│   │
│   ├── session/                    # Conversation persistence
│   │   ├── session.py              # Session dataclass with history replay + trimming
│   │   └── store.py                # SessionStore — JSON file-based persistence
│   │
│   ├── tools/                      # Tool system
│   │   ├── base.py                 # Tool ABC + JSON Schema validation engine
│   │   ├── registry.py             # ToolRegistry — registration, lookup, execution
│   │   └── weather.py              # Example: WeatherTool implementation
│   │
│   ├── config/                     # Configuration
│   │   └── schema.py               # Pydantic schemas (AgentDefaults, ProviderConfig)
│   │
│   ├── templates/                  # Persona templates
│   │   ├── SOUL.md                 # Agent personality & core principles
│   │   ├── AGENT.md                # Agent capabilities prompt
│   │   └── USER.md                 # User context template
│   │
│   └── utils/                      # Shared utilities
│       └── helpers.py              # Message builders, text truncation, workspace sync
│
├── pyproject.toml                  # Project metadata & dependencies
├── CONTRIBUTING.md                 # Contribution guidelines
├── README.md                       # This file
└── assets/
    └── banner.png                  # Repository banner
```

---

## Extending

### Adding a New Tool

Create a class that inherits from `Tool` and define its JSON Schema:

```python
from AgentX.tools.base import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The input query"},
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> str:
        query = kwargs["query"]
        return f"Result for: {query}"
```

Register it:

```python
from AgentX.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register(MyTool())
```

### Adding a New LLM Provider

Implement the `LLMProvider` abstract base class:

```python
from AgentX.providers.base import LLMProvider, LLMResponse

class MyProvider(LLMProvider):
    async def chat(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        # Your implementation here
        ...

    async def chat_stream(self, messages, tools=None, model=None,
                          on_content_delta=None, **kwargs) -> LLMResponse:
        # Streaming implementation
        ...

    def get_default_model(self) -> str:
        return "my-default-model"
```

### Programmatic Usage

Use `AgentCoreLoop` directly in your own application:

```python
import asyncio
from AgentX.agent.loop import AgentCoreLoop
from AgentX.bus import MessageBus, InboundMessage
from AgentX.session import SessionStore

async def main():
    bus = MessageBus()
    loop = AgentCoreLoop(bus=bus, provider=my_provider, workspace=None)
    loop.tools = my_tools

    # Start the bus-driven loop
    task = asyncio.create_task(loop.run())

    # Publish a message
    await bus.publish_inbound(InboundMessage(
        channel="api", sender_id="user", chat_id="conv1",
        content="Hello, AgentX!",
    ))

    # Consume the response
    response = await bus.consume_outbound()
    print(response.content)

    # Shut down
    loop.stop()
    await task

asyncio.run(main())
```

---

## Configuration

Configuration is managed via `AgentDefaults` in [`config/schema.py`](AgentX/config/schema.py):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model` | `qwen3.5:4b-mlx` | Default LLM model |
| `provider` | `auto` | LLM provider selection |
| `max_tool_iterations` | `200` | Max tool-call rounds per turn |
| `max_tool_result_chars` | `16,000` | Truncation limit for tool outputs |
| `max_history_messages` | `50` | Session history window size |
| `session_dir` | `~/.AgentX/sessions` | Where session JSON files are stored |
| `workspace` | `~/.AgentX/workspace` | Agent workspace directory |
| `bot_name` | `Sara` | Display name in CLI |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| [openai](https://github.com/openai/openai-python) | OpenAI-compatible API client |
| [httpx](https://www.python-httpx.org/) | Async HTTP client |
| [rich](https://github.com/Textualize/rich) | Terminal formatting, Live rendering, panels |
| [typer](https://typer.tiangolo.com/) | CLI framework |
| [prompt-toolkit](https://python-prompt-toolkit.readthedocs.io/) | Interactive input with history |
| [pydantic](https://docs.pydantic.dev/) | Configuration validation |
| [loguru](https://github.com/Delgan/loguru) | Structured logging |

---

## Roadmap

- [ ] Multi-provider support (OpenAI, Anthropic, Google, Groq)
- [ ] Semantic memory with vector embeddings
- [ ] MCP (Model Context Protocol) tool integration
- [ ] Web / API server mode
- [ ] Telegram, Discord, Slack channel adapters
- [ ] Checkpoint & replay for long-running tasks
- [ ] Agent-to-agent delegation

---

## Contributing

We welcome contributions! See [**CONTRIBUTING.md**](CONTRIBUTING.md) for guidelines on:

- Setting up the development environment
- Writing new tools and providers
- Code style and commit conventions
- Pull request process

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  <sub>Built with ❤️ by the AgentX community</sub>
</p>
