import asyncio
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

try:
    import feedparser
    import httpx
    HAS_NEWS = True
except ImportError:
    HAS_NEWS = False

class NewsPlugin(Plugin):
    """News aggregation plugin using RSS feeds."""

    def __init__(self):
        super().__init__("news")
        self.enabled = HAS_NEWS
        self.feeds = {
            "bbc": "http://feeds.bbc.co.uk/news/rss.xml",
            "cnn": "http://feeds.cnn.com/cnn/cnn_topstories.rss",
            "hackernews": "https://news.ycombinator.com/rss",
            "techcrunch": "https://techcrunch.com/feed/",
        }

    async def initialize(self) -> None:
        """Initialize news plugin."""
        if not HAS_NEWS:
            logger.warning("News plugin dependencies not installed")
            self.enabled = False

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        """Return news tools."""
        return [
            (
                ToolDefinition(
                    name="get_news",
                    description="Get news articles from various sources",
                    parameters={
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "News source (bbc, cnn, hackernews, techcrunch)"},
                            "limit": {"type": "integer", "description": "Number of articles", "default": 5}
                        },
                        "required": ["source"],
                    },
                ),
                self.get_news,
            ),
        ]

    async def get_news(self, source: str, limit: int = 5) -> list[dict]:
        """Get news from a specific source."""
        if not self.enabled:
            return []

        try:
            if source.lower() not in self.feeds:
                return [{"error": f"Unknown source: {source}"}]

            feed_url = self.feeds[source.lower()]
            feed = await asyncio.to_thread(feedparser.parse, feed_url)

            articles = []
            for entry in feed.entries[:limit]:
                articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", "")[:200],
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })

            return articles
        except Exception as e:
            logger.error(f"Get news error: {e}")
            return [{"error": str(e)}]
