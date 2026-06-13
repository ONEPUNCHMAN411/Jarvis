
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class BrowserPlugin(Plugin):
    """Headless browser tools: navigate, search, extract, interact."""

    def __init__(self):
        super().__init__("browser")
        self._agent = None

    async def _get_agent(self):
        if self._agent is None:
            from jarvis.brain.browser_agent import get_browser_agent
            self._agent = get_browser_agent(headless=True)
        if not self._agent.ready:
            await self._agent.start()
        return self._agent

    async def initialize(self) -> None:
        try:
            from jarvis.brain.browser_agent import _PW_AVAILABLE
            if not _PW_AVAILABLE:
                raise ImportError("playwright not installed")
            # Don't launch Chromium at startup — lazy-start on first tool use
            logger.info("BrowserPlugin ready (Playwright Chromium, lazy-start)")
        except Exception as e:
            self.enabled = False
            logger.warning(f"BrowserPlugin disabled: {e}")

    async def shutdown(self) -> None:
        if self._agent and self._agent.ready:
            await self._agent.stop()

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="navigate_to",
                    description="Navigate the browser to a URL and return the page title and text content.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL to navigate to"},
                        },
                        "required": ["url"],
                    },
                ),
                self.navigate_to,
            ),
            (
                ToolDefinition(
                    name="browser_search",
                    description=(
                        "Search the web using a real browser (Google or Bing). "
                        "Handles JavaScript-heavy pages that simple HTTP requests miss. "
                        "Use search_web for fast lightweight lookups."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "engine": {
                                "type": "string",
                                "enum": ["google", "bing"],
                                "description": "Search engine (default: google)",
                            },
                        },
                        "required": ["query"],
                    },
                ),
                self.browser_search,
            ),
            (
                ToolDefinition(
                    name="browser_get_page",
                    description=(
                        "Fetch the full rendered text of any webpage URL using a real browser. "
                        "Handles JS-rendered content. For plain HTML pages use get_webpage_content."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "Page URL to fetch"},
                        },
                        "required": ["url"],
                    },
                ),
                self.browser_get_page,
            ),
            (
                ToolDefinition(
                    name="click_element",
                    description="Click an element on the current page using a CSS selector.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string", "description": "CSS selector to click"},
                        },
                        "required": ["selector"],
                    },
                ),
                self.click_element,
            ),
            (
                ToolDefinition(
                    name="fill_form",
                    description="Fill an input field on the current page using a CSS selector.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string", "description": "CSS selector of the input"},
                            "text": {"type": "string", "description": "Text to type"},
                        },
                        "required": ["selector", "text"],
                    },
                ),
                self.fill_form,
            ),
            (
                ToolDefinition(
                    name="get_page_links",
                    description="Get all links on the current browser page.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.get_page_links,
            ),
            (
                ToolDefinition(
                    name="browser_back",
                    description="Go back to the previous page in browser history.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.browser_back,
            ),
            (
                ToolDefinition(
                    name="run_javascript",
                    description="Execute JavaScript on the current page and return the result.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "JS code to run"},
                        },
                        "required": ["code"],
                    },
                ),
                self.run_javascript,
            ),
        ]

    async def navigate_to(self, url: str) -> str:
        agent = await self._get_agent()
        r = await agent.navigate(url)
        if not r["success"]:
            return f"Navigation failed: {r.get('error', 'unknown')}"
        return f"[{r['title']}]\nURL: {r['url']}\n\n{r['text']}"

    async def browser_search(self, query: str, engine: str = "google") -> str:
        agent = await self._get_agent()
        r = await agent.search(query, engine=engine)
        if not r["success"]:
            return f"Search failed: {r.get('error', 'unknown')}"
        if not r["results"]:
            return f"No results for '{query}'."
        lines = [f"Results for: {query}\n"]
        for i, res in enumerate(r["results"], 1):
            lines.append(f"{i}. {res['title']}\n   {res['url']}")
            if res.get("snippet"):
                lines.append(f"   {res['snippet']}")
            lines.append("")
        return "\n".join(lines)

    async def browser_get_page(self, url: str) -> str:
        agent = await self._get_agent()
        r = await agent.get_page_text(url)
        if not r["success"]:
            return f"Failed: {r.get('error', 'unknown')}"
        return f"[{r['title']}]\nURL: {r['url']}\n\n{r['text']}"

    async def click_element(self, selector: str) -> str:
        agent = await self._get_agent()
        r = await agent.click(selector)
        return f"Clicked. Now at: {r.get('url', '')}" if r["success"] else f"Click failed: {r.get('error')}"

    async def fill_form(self, selector: str, text: str) -> str:
        agent = await self._get_agent()
        r = await agent.fill(selector, text)
        return "Field filled." if r["success"] else f"Fill failed: {r.get('error')}"

    async def get_page_links(self) -> str:
        agent = await self._get_agent()
        links = await agent.get_links()
        if not links:
            return "No links found."
        return "\n".join(f"  {l['text']} → {l['url']}" for l in links)

    async def browser_back(self) -> str:
        agent = await self._get_agent()
        r = await agent.go_back()
        return f"Back. Now at: {r.get('url', '')}" if r["success"] else f"Failed: {r.get('error')}"

    async def run_javascript(self, code: str) -> str:
        agent = await self._get_agent()
        r = await agent.run_js(code)
        return f"Result: {r['result']}" if r["success"] else f"JS error: {r.get('error')}"
