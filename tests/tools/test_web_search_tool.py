import pytest

from AgentX.tools.web import WebSearchTool, WebSearchConfig
from AgentX.config.schema import Base

def _tool(
    provider: str = "duckduckgo",
    api_key: str = "",
    base_url: str = "",
) -> WebSearchTool:
    return WebSearchTool(
        config=WebSearchConfig(provider=provider, api_key=api_key, base_url=base_url),
    )

@pytest.mark.asyncio
async def test_duckduckgo_search(monkeypatch):

    class MockDDGS:
        def __init__(self, **kwargs):
            pass

        def text(self, query, max_results=5):
            return [
                {
                    "title": "DDG Result",
                    "href": "https://ddg.example",
                    "body": "From DuckDuckGo",
                }
            ]

    monkeypatch.setattr("ddgs.DDGS", MockDDGS)

    tool = WebSearchTool()
    result = await tool.execute("hello", 5)

    assert "DDG Result" in result
