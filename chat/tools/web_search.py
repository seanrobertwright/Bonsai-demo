"""Web search tool — DuckDuckGo (default) or SerpAPI."""

from chat.config import get_config


class WebSearchTool:
    @property
    def definition(self) -> dict:
        return {
            "name": "web_search",
            "description": "Search the internet for current information. Returns top 5 results with title, snippet, and URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    }
                },
                "required": ["query"],
            },
        }

    async def execute(self, params: dict) -> dict:
        query = params.get("query", "").strip()
        if not query:
            return {"error": "Empty search query"}

        cfg = get_config()
        if cfg.get("serpapi_key"):
            return await self._serpapi_search(query, cfg["serpapi_key"])
        return await self._ddg_search(query)

    async def _ddg_search(self, query: str) -> dict:
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=5))
            results = [
                {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
                for r in raw
            ]
            return {"results": results}
        except Exception as e:
            return {"error": f"Search failed: {e}"}

    async def _serpapi_search(self, query: str, api_key: str) -> dict:
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://serpapi.com/search",
                    params={"q": query, "api_key": api_key, "num": 5},
                )
                data = resp.json()
            results = [
                {"title": r.get("title", ""), "snippet": r.get("snippet", ""), "url": r.get("link", "")}
                for r in data.get("organic_results", [])[:5]
            ]
            return {"results": results}
        except Exception as e:
            return {"error": f"SerpAPI search failed: {e}"}
