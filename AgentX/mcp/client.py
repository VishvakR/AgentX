import asyncio
import httpx
import re
from loguru import logger
from contextlib import AsyncExitStack

from AgentX.tools.registry import Tool, ToolRegistry

_SANITIZE_RE = re.compile(r"_+")
def _sanitize_name(name: str) -> str:
    """Sanitize an MCP-derived name for model API compatibility."""
    return _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", name))

class _MCPBaseWrapper(Tool):
    def _set_mcp_connection(self, session, server_name: str):
        self._session = session
        self._server_name = server_name


class MCPToolWrappper(_MCPBaseWrapper):

    def __init__(self, session, server_name: str, tool_def, time_out: int = 30):
        self._set_mcp_connection(session, server_name)



async def connect_mcp_servers(mcp_servers: dict, registry: ToolRegistry):
    server_stacks = dict[str, AsyncExitStack] = {}

    async def connect_server(name: str, cfg):
        pass

    for name, cfg in mcp_servers.items():
        try:
            result = await connect_server(name, cfg)
        except Exception as e:
            logger.exception("MCP server '{}' connection failed: {}", name, e)
            continue
        if result is not None and result[1] is not None:
            server_stacks[result[0]] = result[1]

    return server_stacks
