
import threading

from loguru import logger

try:
    from playwright.async_api import async_playwright, Browser, Page, Playwright
    _PW_AVAILABLE = True
except ImportError:
    _PW_AVAILABLE = False


class BrowserAgent:
    """Headless Playwright browser for navigation and scraping."""

    def __init__(self, headless: bool = True):
        if not _PW_AVAILABLE:
            raise ImportError(
                "playwright is required. Run: pip install playwright && playwright install chromium"
            )
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        await self._page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        logger.info("BrowserAgent started (headless Chromium)")

    async def stop(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            logger.warning(f"BrowserAgent browser close failed: {e}")
        finally:
            if self._pw:
                try:
                    await self._pw.stop()
                except Exception as e:
                    logger.warning(f"BrowserAgent playwright stop failed: {e}")
            self._page = None
            self._browser = None
            self._pw = None
            logger.info("BrowserAgent stopped")

    async def _ensure_page(self) -> Page:
        if not self._page:
            raise RuntimeError("BrowserAgent not started — call start() first.")
        return self._page

    async def navigate(self, url: str) -> dict:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        page = await self._ensure_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            title = await page.title()
            text = await page.evaluate("() => document.body?.innerText || ''")
            return {"url": page.url, "title": title, "text": text[:6000], "success": True}
        except Exception as e:
            logger.warning(f"BrowserAgent.navigate failed: {e}")
            return {"url": url, "title": "", "text": "", "success": False, "error": str(e)}

    async def search(self, query: str, engine: str = "google") -> dict:
        q = query.replace(" ", "+")
        url = (
            f"https://www.google.com/search?q={q}"
            if engine == "google"
            else f"https://www.bing.com/search?q={q}"
        )
        page = await self._ensure_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            if engine == "google":
                results = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('div.g')).slice(0, 6).map(el => ({
                        title:   el.querySelector('h3')?.innerText || '',
                        url:     el.querySelector('a')?.href || '',
                        snippet: el.querySelector('.VwiC3b, .lEBKkf')?.innerText || ''
                    })).filter(r => r.title && r.url.startsWith('http'))
                """)
            else:
                results = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('.b_algo')).slice(0, 6).map(el => ({
                        title:   el.querySelector('h2')?.innerText || '',
                        url:     el.querySelector('a')?.href || '',
                        snippet: el.querySelector('.b_caption p')?.innerText || ''
                    })).filter(r => r.title)
                """)
            return {"query": query, "results": results, "success": True}
        except Exception as e:
            logger.warning(f"BrowserAgent.search failed: {e}")
            return {"query": query, "results": [], "success": False, "error": str(e)}

    async def get_page_text(self, url: str) -> dict:
        return await self.navigate(url)

    async def click(self, selector: str) -> dict:
        page = await self._ensure_page()
        try:
            await page.click(selector, timeout=8_000)
            await page.wait_for_load_state("domcontentloaded")
            return {"success": True, "url": page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def fill(self, selector: str, text: str) -> dict:
        page = await self._ensure_page()
        try:
            await page.fill(selector, text, timeout=8_000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def screenshot(self) -> bytes | None:
        page = await self._ensure_page()
        try:
            return await page.screenshot(type="png", full_page=False)
        except Exception as e:
            logger.warning(f"BrowserAgent.screenshot failed: {e}")
            return None

    async def get_links(self) -> list[dict]:
        page = await self._ensure_page()
        try:
            return await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .slice(0, 25)
                    .map(a => ({ text: a.innerText.trim().slice(0, 80), url: a.href }))
                    .filter(l => l.text && l.url.startsWith('http'))
            """)
        except Exception:
            return []

    async def go_back(self) -> dict:
        page = await self._ensure_page()
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=10_000)
            return {"success": True, "url": page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def run_js(self, code: str) -> dict:
        page = await self._ensure_page()
        try:
            # Pass code directly — Playwright handles expressions and function strings
            result = await page.evaluate(code)
            return {"success": True, "result": str(result)[:2000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @property
    def current_url(self) -> str:
        return self._page.url if self._page else ""

    @property
    def ready(self) -> bool:
        return self._page is not None


_agent: BrowserAgent | None = None
_agent_lock = threading.Lock()


def get_browser_agent(headless: bool = True) -> BrowserAgent:
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = BrowserAgent(headless=headless)
    return _agent
