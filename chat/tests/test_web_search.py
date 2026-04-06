import pytest
from chat.tools.web_search import WebSearchTool


@pytest.fixture
def search():
    return WebSearchTool()


def test_definition(search):
    d = search.definition
    assert d["name"] == "web_search"


@pytest.mark.asyncio
async def test_empty_query(search):
    result = await search.execute({"query": ""})
    assert "error" in result
