import asyncio
import httpx
import re
import os
from loguru import logger
from contextlib import AsyncExitStack

from AgentX.tools.registry import Tool, ToolRegistry

_SANITIZE_RE = re.compile(r"_+")
def _sanitize_name(name: str) -> str:
    """Sanitize an MCP-derived name for model API compatibility."""
    return _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", name))

def _normalize__stdio_command(
        command: str,
        args: list[str],
        env: dict[str, str] | None,
    ) -> tuple[str, list[str], dict[str, str] | None]:
    normalized_args = list(args or [])
    if os.name != 'nt':
        return command, normalized_args, env 

class _MCPBaseWrapper(Tool):
    def _set_mcp_connection(self, session, server_name: str):
        self._session = session
        self._server_name = server_name


class MCPToolWrappper(_MCPBaseWrapper):

    def __init__(self, session, server_name: str, tool_def, time_out: int = 30):
        self._set_mcp_connection(session, server_name)



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
                if cfg.commmand:
                    transport_type = "stdio"
                elif cfg.url:
                    transport_type = "sse" if cfg.url.rstrip("/").endswith("/sse") else "streamableHttp"
                else:
                    logger.warning("MCP server '{}': no command or url configured, skipping", name)
                    # await server_stack.aclose()
                    return name, None
                
            if transport_type in {"sse", "streamableHttp"}:
                #need to implement
                pass
            if transport_type == "stdio":
                command, args, env = _normalize__stdio_command(
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
                # Yet to implement
                pass
            elif transport_type == "streamableHttp":
                # yet to implement
                pass

            else:
                logger.warning("MCP server '{}': unknown transport type '{}'", name, transport_type)
                await server_stack.aclose()
                return name, None
            
            session = await server_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            tools = await session.list_tools()

        
        except Exception as e:
            pass

    server_stacks = dict[str, AsyncExitStack] = {}
    for name, cfg in mcp_servers.items():
        try:
            result = await connect_server(name, cfg)
        except Exception as e:
            logger.exception("MCP server '{}' connection failed: {}", name, e)
            continue
        if result is not None and result[1] is not None:
            server_stacks[result[0]] = result[1]

    return server_stacks
