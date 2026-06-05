from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

try:
    import httpx
    from bs4 import BeautifulSoup
    HAS_WEB_SEARCH = True
except ImportError:
    HAS_WEB_SEARCH = False

class WebSearchPlugin(Plugin):
    """Web search with context extraction plugin."""

    def __init__(self):
        super().__init__("web_search")
        self.enabled = HAS_WEB_SEARCH

    async def initialize(self) -> None:
        """Initialize web search plugin."""
        if not HAS_WEB_SEARCH:
            logger.warning("Web search dependencies not installed")
            self.enabled = False

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="get_webpage_content",
                    description="Get the content of a specific webpage",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL to fetch"}
                        },
                        "required": ["url"],
                    },
                ),
                self.get_webpage_content,
            ),
        ]

    async def search_web(self, query: str) -> list[dict]:
        """Search the web using Google."""
        if not self.enabled:
            return []

        try:
            async with httpx.AsyncClient() as client:
                url = f"https://www.google.com/search"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                params = {"q": query}

                response = await client.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                results = []

                for result in soup.find_all("div", class_="g")[:5]:
                    title_elem = result.find("h3")
                    url_elem = result.find("a")
                    snippet_elem = result.find("span", class_="st")

                    if title_elem and url_elem:
                        results.append({
                            "title": title_elem.get_text(),
                            "url": url_elem.get("href", ""),
                            "snippet": snippet_elem.get_text() if snippet_elem else "",
                        })

                return results
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return []

    async def get_webpage_content(self, url: str) -> str:
        """Get the text content of a webpage."""
        if not self.enabled:
            return "Web search not available"

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = await client.get(url, headers=headers, timeout=10)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                for script in soup(["script", "style"]):
                    script.decompose()

                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = "\n".join(chunk for chunk in chunks if chunk)

                return text[:2000]
        except Exception as e:
            logger.error(f"Get webpage error: {e}")
            return f"Failed to fetch webpage: {str(e)}"
