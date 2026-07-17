import asyncio
import httpx
import re
import os
from loguru import logger
from contextlib import AsyncExitStack
from typing import Any

from AgentX.tools.registry import Tool, ToolRegistry

_SANITIZE_RE = re.compile(r"_+")
def _sanitize_name(name: str) -> str:
    """Sanitize an MCP-derived name for model API compatibility."""
    return _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", name))

def _normalize_stdio_command(
        command: str,
        args: list[str],
        env: dict[str, str] | None,
    ) -> tuple[str, list[str], dict[str, str] | None]:
    normalized_args = list(args or [])
    if os.name != 'nt':
        return command, normalized_args, env
    # Windows: no special normalization needed yet.
    return command, normalized_args, env
    
def _extract_nullable_branch(options: Any) -> tuple[dict[str, Any], bool] | None:
    """Return the single non-null branch for nullable unions."""
    if not isinstance(options, list):
        return None

    non_null: list[dict[str, Any]] = []
    saw_null = False
    for option in options:
        if not isinstance(option, dict):
            return None
        if option.get("type") == "null":
            saw_null = True
            continue
        non_null.append(option)

    if saw_null and len(non_null) == 1:
        return non_null[0], True
    return None

def _normalize_schema_for_openai(schema: Any) -> dict[str, Any]:
    """Normalize only nullable JSON Schema patterns for tool definitions."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    normalized = dict(schema)

    raw_type = normalized.get("type")
    if isinstance(raw_type, list):
        non_null = [item for item in raw_type if item != "null"]
        if "null" in raw_type and len(non_null) == 1:
            normalized["type"] = non_null[0]
            normalized["nullable"] = True

    for key in ("oneOf", "anyOf"):
        nullable_branch = _extract_nullable_branch(normalized.get(key))
        if nullable_branch is not None:
            branch, _ = nullable_branch
            merged = {k: v for k, v in normalized.items() if k != key}
            merged.update(branch)
            normalized = merged
            normalized["nullable"] = True
            break

    if "properties" in normalized and isinstance(normalized["properties"], dict):
        normalized["properties"] = {
            name: _normalize_schema_for_openai(prop) if isinstance(prop, dict) else prop
            for name, prop in normalized["properties"].items()
        }

    if "items" in normalized and isinstance(normalized["items"], dict):
        normalized["items"] = _normalize_schema_for_openai(normalized["items"])

    if normalized.get("type") != "object":
        return normalized

    normalized.setdefault("properties", {})
    normalized.setdefault("required", [])
    return normalized

class _MCPBaseWrapper(Tool):
    def _set_mcp_connection(self, session, server_name: str):
        self._session = session
        self._server_name = server_name


class MCPToolWrapper(_MCPBaseWrapper):

    def __init__(self, session, server_name: str, tool_def, time_out: int = 30):
        self._set_mcp_connection(session, server_name)
        self._original_name = tool_def.name
        self._name = _sanitize_name(f"mcp_{server_name}_{tool_def.name}")
        self._description = tool_def.description or tool_def.name
        raw_schema = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._parameters = _normalize_schema_for_openai(raw_schema)
        self._tool_timeout = time_out

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._original_name, arguments=kwargs),
                timeout=self._tool_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "MCP tool '{}' timed out after {}s", self._name, self._tool_timeout
            )
            return f"(MCP tool call timed out after {self._tool_timeout}s)"
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling() > 0:
                raise
            logger.warning("MCP tool '{}' was cancelled by server/SDK", self._name)
            return "(MCP tool call was cancelled)"
        except Exception as exc:
            logger.exception(
                "MCP tool '{}' failed: {}",
                self._name,
                type(exc).__name__,
            )
            return f"(MCP tool call failed: {type(exc).__name__})"

        if not result.content:
            return ""

        parts: list[str] = []
        for item in result.content:
            if hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "\n".join(parts)

            



async def connect_mcp_servers(mcp_servers: dict, registry: ToolRegistry):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client
    from mcp.client.sse import sse_client


    async def connect_server(name: str, cfg):
        server_stack =  AsyncExitStack()
        await server_stack.__aenter__()
        try:
            transport_type = cfg.type
            if not transport_type:
                if cfg.command:
                    transport_type = "stdio"
                elif cfg.url:
                    transport_type = "sse" if cfg.url.rstrip("/").endswith("/sse") else "streamableHttp"
                else:
                    logger.warning("MCP server '{}': no command or url configured, skipping", name)
                    # await server_stack.aclose()
                    return name, None
                
            if transport_type == "stdio":
                command, args, env = _normalize_stdio_command(
                    cfg.command, cfg.args, cfg.env or None
                )
                params = StdioServerParameters(
                     command=command,
                     args=args,
                     env=env,
                     cwd=cfg.cwd or None
                 )
                read, write = await server_stack.enter_async_context(stdio_client(params))
            elif transport_type == "sse":
                logger.warning("MCP server '{}': SSE transport not yet implemented, skipping", name)
                await server_stack.aclose()
                return name, None
            elif transport_type == "streamableHttp":
                logger.warning("MCP server '{}': streamableHttp transport not yet implemented, skipping", name)
                await server_stack.aclose()
                return name, None
            else:
                logger.warning("MCP server '{}': unknown transport type '{}'", name, transport_type)
                await server_stack.aclose()
                return name, None
            
            session = await server_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            tools = await session.list_tools()
            registered_count = 0
            enabled_tools = set(cfg.enabled_tools)
            allow_all_tools = "*" in enabled_tools
            matched_enabled_tools: set[str] = set()
            available_raw_names = [tool_def.name for tool_def in tools.tools]
            available_wrapped_names = [f"mcp_{name}_{tool_def.name}" for tool_def in tools.tools]
            for tool_def in tools.tools:
                wrapped_name = f"mcp_{name}_{tool_def.name}"
                if (
                    not allow_all_tools
                    and tool_def.name not in enabled_tools
                    and wrapped_name not in enabled_tools
                ):
                    logger.debug(
                        "MCP: skipping tool '{}' from server '{}' (not in enabledTools)",
                        wrapped_name,
                        name,
                    )
                    continue
                wrapper = MCPToolWrapper(session, name, tool_def, time_out=cfg.tool_timeout)
                registry.register(wrapper)
                logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, name)
                registered_count += 1
                if enabled_tools:
                    if tool_def.name in enabled_tools:
                        matched_enabled_tools.add(tool_def.name)
                    if wrapped_name in enabled_tools:
                        matched_enabled_tools.add(wrapped_name)
            if enabled_tools and not allow_all_tools:
                unmatched_enabled_tools = sorted(enabled_tools - matched_enabled_tools)
                if unmatched_enabled_tools:
                    logger.warning(
                        "MCP server '{}': enabledTools entries not found: {}. Available raw names: {}. "
                        "Available wrapped names: {}",
                        name,
                        ", ".join(unmatched_enabled_tools),
                        ", ".join(available_raw_names) or "(none)",
                        ", ".join(available_wrapped_names) or "(none)",
                    )

            logger.info(
                "MCP server '{}': connected, {} capabilities registered", name, registered_count
            )
            return name, server_stack
        except Exception as e:
            logger.exception("Failed to connect to MCP server '{}': {}", name, e)
            await server_stack.aclose()
            return name, None

    server_stacks: dict[str, AsyncExitStack] = {}
    tasks: list[asyncio.Task] = []
    for name, cfg in mcp_servers.items():
        task = asyncio.create_task(connect_server(name, cfg))
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        name = list(mcp_servers.keys())[i]
        if isinstance(result, BaseException):
            if not isinstance(result, asyncio.CancelledError):
                logger.error("MCP server '{}' connection task failed: {}", name, result)
        elif result is not None and result[1] is not None:
            server_stacks[result[0]] = result[1]

    return server_stacks

