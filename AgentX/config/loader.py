# AgentX/config/loader.py
import json
from AgentX.config.schema import MCPServerConfig

def load_mcp_servers(data: dict) -> dict[str, MCPServerConfig]:
    servers = {}

    for name, cfg in data.get("mcpServers", {}).items():
        servers[name] = MCPServerConfig(**cfg)
        
    return servers