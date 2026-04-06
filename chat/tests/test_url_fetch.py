import pytest
from chat.tools.url_fetch import URLFetchTool


@pytest.fixture
def fetcher():
    return URLFetchTool()


def test_definition(fetcher):
    assert fetcher.definition["name"] == "url_fetch"


@pytest.mark.asyncio
async def test_invalid_url(fetcher):
    result = await fetcher.execute({"url": "not-a-url"})
    assert "error" in result


@pytest.mark.asyncio
async def test_empty_url(fetcher):
    result = await fetcher.execute({"url": ""})
    assert "error" in result
