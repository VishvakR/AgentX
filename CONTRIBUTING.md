# Contributing to AgentX

First off, thank you for considering contributing to **AgentX**! Every contribution — code, docs, bug reports, or ideas — helps build a better framework for everyone.

AgentX is an extensible AI agent framework for building production-ready autonomous agents with support for multiple LLM providers, tool execution, streaming responses, and session persistence.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Guidelines](#coding-guidelines)
- [Writing New Tools](#writing-new-tools)
- [Adding New Providers](#adding-new-providers)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)
- [Feature Requests](#feature-requests)
- [Good First Issues](#good-first-issues)

---

## Code of Conduct

We are committed to providing a welcoming and inclusive environment for everyone. By participating in this project, you agree to:

- **Be respectful** — Treat everyone with dignity. No harassment, discrimination, or personal attacks.
- **Be constructive** — Focus on the work. Offer helpful feedback and accept it graciously.
- **Be collaborative** — Share knowledge, help newcomers, and celebrate each other's contributions.

If you witness or experience unacceptable behavior, please open an issue or contact a maintainer directly.

---

## Ways to Contribute

There are many ways to help, regardless of your experience level:

| Area | Examples |
|------|----------|
| 🐛 **Bug Fixes** | Fix broken imports, logic errors, edge cases |
| 🔧 **New Tools** | Build tools (web search, file I/O, code execution, etc.) |
| 🔌 **Providers** | Add support for new LLM backends (Anthropic, Google, Groq, etc.) |
| 💬 **Session & Memory** | Improve history management, add semantic memory |
| 🖥️ **CLI** | Add slash commands, improve rendering, add themes |
| 📨 **Channels** | Build adapters (Telegram, Discord, Slack, REST API) |
| 📖 **Documentation** | Improve README, add tutorials, write docstrings |
| ✅ **Testing** | Write unit tests, integration tests, end-to-end tests |
| ⚡ **Performance** | Optimize streaming, reduce latency, improve concurrency |

---

## Getting Started

### 1. Fork & Clone

```bash
# Fork via GitHub, then:
git clone https://github.com/<your-username>/AgentX.git
cd AgentX
```

### 2. Create a Feature Branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b fix/bug-description
```

### 3. Install Dependencies

```bash
# Recommended: use uv for fast, reproducible installs
uv sync

# Alternative: pip
pip install -e .
```

### 4. Verify Setup

```bash
# Run the CLI to confirm everything works
uv run python -m AgentX.main agent --help

# Run a quick test
uv run python -m AgentX.main agent -m "Hello, AgentX!"
```

---

## Development Setup

### Recommended Tools

| Tool | Purpose | Required |
|------|---------|----------|
| **Python 3.13+** | Runtime | ✅ |
| **[uv](https://docs.astral.sh/uv/)** | Package manager & virtual environment | ✅ |
| **Git** | Version control | ✅ |
| **[Ruff](https://docs.astral.sh/ruff/)** | Linting & formatting | Recommended |
| **[Pyright](https://github.com/microsoft/pyright)** | Static type checking | Optional |
| **VS Code / PyCharm** | IDE | Optional |
| **[Ollama](https://ollama.ai)** | Local LLM backend for testing | Recommended |

### Environment Variables

```bash
# Optional: configure LLM timeout (default: 300s)
export AGENTX_LLM_TIMEOUT_S=300

# Optional: for non-Ollama providers
export OPENAI_API_KEY=sk-...
```

### Running with Verbose Logging

```bash
# Shows full debug output (session, state transitions, tool calls)
uv run python -m AgentX.main agent -v
```

---

## Project Structure

Understanding the architecture will help you contribute effectively:

```
AgentX/
├── agent/                  # Core agent logic
│   ├── loop.py             # AgentCoreLoop — state machine (RESTORE→BUILD→RUN→SAVE→RESPOND)
│   ├── runner.py           # AgentRunner — LLM call loop with tool execution
│   ├── context.py          # ContextBuilder — assembles system prompt + history
│   └── hook.py             # Lifecycle hook context
│
├── bus/                    # Message transport layer
│   ├── bus.py              # MessageBus — async inbound/outbound queues
│   └── messages.py         # InboundMessage / OutboundMessage dataclasses
│
├── cli/                    # Terminal interface
│   ├── command.py          # Typer CLI — REPL + single-message mode
│   ├── stream.py           # StreamRenderer — Rich Live streaming
│   └── banner.py           # ASCII art banner
│
├── providers/              # LLM provider abstraction
│   ├── base.py             # LLMProvider ABC, LLMResponse, ToolCallRequest
│   ├── openai_compat_provider.py  # OpenAI-compatible (Ollama, OpenAI, etc.)
│   └── registry.py         # Provider auto-detection
│
├── session/                # Conversation persistence
│   ├── session.py          # Session dataclass (history, trimming, replay)
│   └── store.py            # SessionStore — JSON file-based storage
│
├── tools/                  # Tool system
│   ├── base.py             # Tool ABC + JSON Schema validation
│   ├── registry.py         # ToolRegistry — register, lookup, execute
│   └── weather.py          # Reference implementation (WeatherTool)
│
├── config/                 # Configuration
│   └── schema.py           # Pydantic models (AgentDefaults, ProviderConfig)
│
├── templates/              # Persona templates
│   ├── SOUL.md             # Agent personality & principles
│   ├── AGENT.md            # Agent capabilities
│   └── USER.md             # User context
│
└── utils/                  # Shared utilities
    └── helpers.py          # Message builders, text truncation
```

### Key Data Flow

```
InboundMessage → MessageBus → AgentCoreLoop.run()
    → RESTORE (load session) → BUILD (assemble messages) → RUN (call LLM)
    → SAVE (persist session) → RESPOND (build outbound)
→ MessageBus → OutboundMessage → CLI / API / Bot
```

---

## Coding Guidelines

### General Principles

- **Use type hints** — All function signatures should have full type annotations.
- **Prefer `async`/`await`** — The framework is async-first. Avoid blocking I/O.
- **Keep functions focused** — Each function should do one thing well. Aim for ≤30 lines.
- **Write docstrings** — All public classes and methods need docstrings.
- **Handle errors gracefully** — Use `try`/`except` with specific exception types. Log errors with `loguru`.
- **Preserve existing architecture** — Don't restructure modules unless explicitly discussing it in an issue first.

### Naming Conventions

| Type | Convention | Examples |
|------|-----------|----------|
| **Classes** | `PascalCase` | `AgentRunner`, `WeatherTool`, `SessionStore` |
| **Functions** | `snake_case` | `build_messages()`, `execute_tool()` |
| **Private methods** | `_leading_underscore` | `_dispatch_inbound()`, `_state_restore()` |
| **Constants** | `UPPER_SNAKE_CASE` | `_EXIT_COMMANDS`, `_MAX_LENGTH_RECOVERIES` |
| **Variables** | `snake_case` | `session_key`, `tool_result`, `final_content` |

### Formatting

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Lint
ruff check AgentX/

# Format
ruff format AgentX/

# Fix auto-fixable issues
ruff check --fix AgentX/
```

### Logging

Use `loguru` (not `print()`) for all diagnostic output:

```python
from loguru import logger

# Good
logger.debug("Processing session {!r}", session_key)
logger.info("Agent loop started — waiting for inbound messages")
logger.warning("Max iterations reached ({})", max_iters)
logger.exception("Unexpected error in dispatch")

# Bad
print(f"Processing session {session_key}")
```

---

## Writing New Tools

Each tool is a subclass of `Tool` with a JSON Schema definition. Here's the complete pattern:

```python
from AgentX.tools.base import Tool

class SearchTool(Tool):
    """Web search tool for the agent."""

    name = "web_search"
    description = "Search the web for current information on a topic."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> str:
        query = kwargs["query"]
        num_results = kwargs.get("num_results", 5)
        # Your implementation here
        return f"Search results for: {query}"
```

### Tool Checklist

- [ ] Inherits from `Tool`
- [ ] Has `name` and `description` class attributes
- [ ] Defines `parameters_schema` property with valid JSON Schema
- [ ] `execute()` is async and accepts `**kwargs`
- [ ] Validates inputs (the base class handles schema validation automatically)
- [ ] Returns human-readable string output
- [ ] Handles errors gracefully (returns error message, doesn't raise)
- [ ] Registered in `_build_tools()` in [`cli/command.py`](AgentX/cli/command.py)

---

## Adding New Providers

A provider wraps an LLM API behind the `LLMProvider` interface. You need to implement:

```python
from AgentX.providers.base import LLMProvider, LLMResponse, ToolCallRequest

class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude models."""

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-20250514"):
        super().__init__(api_key=api_key)
        self._default_model = default_model

    async def chat(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        """Non-streaming chat completion."""
        # Convert messages to Anthropic format
        # Make API call
        # Parse response into LLMResponse
        ...

    async def chat_stream(self, messages, tools=None, model=None,
                          on_content_delta=None, **kwargs) -> LLMResponse:
        """Streaming chat completion."""
        # Stream tokens, call on_content_delta(delta) for each chunk
        # Return final LLMResponse when done
        ...

    def get_default_model(self) -> str:
        return self._default_model
```

### Provider Checklist

- [ ] Inherits from `LLMProvider`
- [ ] Implements `chat()` for non-streaming responses
- [ ] Implements `chat_stream()` with `on_content_delta` callback
- [ ] Returns `LLMResponse` with correct `finish_reason` and `tool_calls`
- [ ] Handles errors and returns `LLMResponse(finish_reason="error", ...)`
- [ ] Extracts and reports token usage
- [ ] Keeps provider-specific logic isolated from the agent core

---

## Commit Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/) for clear, machine-readable history:

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

### Types

| Type | When to Use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code restructuring (no feature/fix) |
| `test` | Adding or updating tests |
| `perf` | Performance improvement |
| `chore` | Build, config, dependency updates |
| `style` | Formatting, whitespace (no logic change) |

### Examples

```
feat(tools): add web search tool with rate limiting

fix(cli): resolve duplicate panel rendering on stream end

docs: add tool development guide to CONTRIBUTING.md

refactor(agent): extract state handlers into separate methods

test(session): add history trimming edge case tests

perf(runner): reduce tool execution overhead with batched dispatch

chore: bump openai dependency to 2.40.0
```

### Rules

- **Keep the subject line under 72 characters**
- **Use imperative mood** ("add feature", not "added feature")
- **Reference issues** when applicable: `fix(cli): resolve #42 streaming bug`
- **One logical change per commit** — don't mix unrelated changes

---

## Pull Request Process

### Before Submitting

1. **Ensure your code builds** — `uv run python -m AgentX.main agent --help` should work.
2. **Format your code** — Run `ruff format AgentX/` and `ruff check AgentX/`.
3. **Test your changes** — At minimum, verify the CLI runs end-to-end.
4. **Update documentation** — If you changed behavior, update relevant docstrings and README sections.
5. **Keep changes focused** — One feature or fix per PR. Split large changes into smaller PRs.

### Submitting

1. Push your branch to your fork.
2. Open a pull request against the `main` branch.
3. Fill out the PR template with:

| Section | What to Include |
|---------|-----------------|
| **Description** | What changed and why |
| **Motivation** | The problem this solves or feature this enables |
| **Changes** | List of modified files and what changed in each |
| **Testing** | How you verified the changes work |
| **Screenshots** | Required for any CLI/UI changes |
| **Breaking Changes** | Any backward-incompatible changes |
| **Related Issues** | Link to relevant issues (`Closes #42`) |

### Review Process

- A maintainer will review your PR within a few days.
- Address feedback by pushing additional commits (don't force-push during review).
- Once approved, a maintainer will merge your PR.

---

## Reporting Issues

Good bug reports save everyone time. Please include:

| Field | Details |
|-------|---------|
| **Title** | Clear, specific summary (e.g., "CLI hangs when LLM is unreachable") |
| **Python version** | Output of `python --version` |
| **OS** | macOS / Linux / Windows + version |
| **AgentX version** | `uv run python -m AgentX.main version` |
| **Steps to reproduce** | Minimal, numbered steps to trigger the issue |
| **Expected behavior** | What should happen |
| **Actual behavior** | What actually happens |
| **Logs** | Run with `-v` flag and paste relevant log output |
| **Stack trace** | Full traceback if applicable |

### Issue Template

```markdown
**Environment:**
- Python: 3.13.x
- OS: macOS 15.x
- AgentX: 0.1.0

**Steps to reproduce:**
1. Run `uv run python -m AgentX.main agent`
2. Type "..."
3. Observe...

**Expected:** ...
**Actual:** ...

**Logs (with -v flag):**
```
[paste logs here]
```
```

---

## Feature Requests

We love hearing ideas! A good feature request includes:

- **Problem statement** — What problem does this solve? Why is it needed?
- **Proposed solution** — How would you implement it? Which modules are affected?
- **Alternatives considered** — What other approaches did you think about?
- **Use cases** — Who benefits and how?
- **Mockups** — For CLI/UI features, a sketch of the expected output helps.

---

## Good First Issues

If you're new to the project, these are great starting points:

| Difficulty | Task |
|------------|------|
| 🟢 Easy | Add docstrings to undocumented public methods |
| 🟢 Easy | Add a simple built-in tool (e.g., calculator, date/time) |
| 🟢 Easy | Improve error messages for common failures |
| 🟡 Medium | Add a `/switch <session>` slash command to switch sessions |
| 🟡 Medium | Write unit tests for `Session.trim()` edge cases |
| 🟡 Medium | Add a `--format json` output mode for single-message CLI |
| 🔴 Advanced | Implement a new LLM provider (Anthropic, Google, etc.) |
| 🔴 Advanced | Add semantic memory with vector embeddings |
| 🔴 Advanced | Build a REST API server mode alongside the CLI |

Look for issues labeled `good first issue` or `help wanted` in the issue tracker.

---

## Thank You ❤️

Every contribution — whether it's a one-line docs fix, a new tool, a bug report, or a major feature — makes AgentX better for the entire community.

We appreciate your time and effort. Happy coding!

---

<p align="center">
  <sub>Built with ❤️ by the AgentX community</sub>
</p>
