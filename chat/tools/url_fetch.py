"""URL fetch tool — downloads a web page and extracts readable text."""

import httpx
from bs4 import BeautifulSoup

from chat.config import URL_FETCH_MAX_CHARS


class URLFetchTool:
    @property
    def definition(self) -> dict:
        return {
            "name": "url_fetch",
            "description": "Fetch a web page and extract its readable text content. Useful for reading articles, documentation, or any URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    }
                },
                "required": ["url"],
            },
        }

    async def execute(self, params: dict) -> dict:
        url = params.get("url", "").strip()
        if not url:
            return {"error": "Empty URL"}
        if not url.startswith(("http://", "https://")):
            return {"error": f"Invalid URL: {url}"}

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                resp = await client.get(url, headers={"User-Agent": "BonsaiChat/1.0"})
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else url
            text = soup.get_text(separator="\n", strip=True)

            if len(text) > URL_FETCH_MAX_CHARS:
                text = text[:URL_FETCH_MAX_CHARS] + "\n... [truncated]"

            return {"title": title, "text": text}
        except Exception as e:
            return {"error": f"Failed to fetch URL: {e}"}
