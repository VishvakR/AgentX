import asyncio
from typing import Any
import re
import html
from loguru import logger

from AgentX.config.schema import Base
from AgentX.tools.base import Tool, tool_parameters


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()

def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()

def _format_results(query: str, items: list[dict[str, Any]], n: int) -> str:
    """Format provider results into shared plaintext output."""
    if not items:
        return f"No results for: {query}"
    lines = [f"Results for: {query}\n"]
    for i, item in enumerate(items[:n], 1):
        title = _normalize(_strip_tags(item.get("title", "")))
        snippet = _normalize(_strip_tags(item.get("content", "")))
        lines.append(f"{i}. {title}\n   {item.get('url', '')}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)

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
    def __init__(
            self,
            config: WebSearchConfig | None = None
        ):
        self.config = config if config is not None else WebSearchConfig()

    @classmethod
    def config_cls(cls):
        return WebSearchConfig


    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return "Get information from the internet"
    
    @property
    def read_only(self) -> bool:
        return True
    
    async def execute(
            self,
            query: str,
            count: int | None,
            **kwargs: Any,
        ) -> str:
        
        provider = self.config.provider.strip().lower()
        n = min(max(count or self.config.max_result, 1), 10)
        if provider == "duckduckgo":
            return await self._search_duckduckgo(query, n)
        
        #Implement further providers later

    async def _search_duckduckgo(self, query: str, count: int) -> str:
        try:
            from ddgs import DDGS

            ddsg = DDGS(timeout=10)
            raw = await asyncio.wait_for(
                asyncio.to_thread(ddsg.text, query, max_results=count),
                timeout=self.config.timeout,
            )

            if not raw:
                return f"No results for: {query}"
            items = [
                {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
                for r in raw
            ]

            return _format_results(query, items, count)
        
        except Exception as e:
            logger.warning("DuckDuckGo search failed: {}", e)
            return f"Error: DuckDuckGo search failed ({e})"
    


