import asyncio

from AgentX.config.schema import Base
from AgentX.tools.base import Tool, tool_parameters

class WebSearchConfig(Base):
    provider: str = "duckduckgo"
    api_key: str = ""
    base_url: str = ""
    max_result: int = 5
    timeout: int = 30


@tool_parameters(
    {
        "type" : "object",
        "properties" : {
            "query" : {
                "type" : "string",
                "description" : "Query to search infomation from the internet",
            },
            "count" : {
                "type" : "integer",
                "minimum" : 1,
                "maximum" : 5,
                "description" : "Number of top search results"
            },
        },
        "required" : ["query"]
    }
)
class WebSearchTool(Tool):
    pass

