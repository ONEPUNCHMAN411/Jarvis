"""
Managed browser control.

Prefers a persistent Chromium session backed by an installed Windows browser
(Edge/Chrome/Opera) so JARVIS can navigate, click, type, scroll, and inspect
pages deterministically without opening duplicate tabs.
Falls back to the system browser only when structured control is unavailable.
"""


import asyncio
import re
import shutil
import tempfile
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from loguru import logger

import httpx

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    PlaywrightTimeoutError = TimeoutError

_SAFE_URL_SCHEMES = frozenset({"http", "https"})
_BLOCKED_URL_SCHEMES = frozenset({"file", "javascript", "data", "vbscript", "chrome", "about"})

def _validate_url(url: str) -> str:
    """Enforce safe URL schemes. Raises ValueError for dangerous schemes."""
    from urllib.parse import urlparse
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in _BLOCKED_URL_SCHEMES:
        raise ValueError(f"URL scheme '{scheme}://' is not allowed for security reasons.")
    if scheme not in _SAFE_URL_SCHEMES:
        raise ValueError(f"Only http:// and https:// URLs are allowed. Got: '{scheme}://'")
    return url

def _find_browser_executable() -> str | None:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / r"AppData\Local\Programs\Opera GX\opera.exe",
        Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    for name in ("msedge", "chrome", "opera"):
        found = shutil.which(name)
        if found:
            return found
    return None

class Browser:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self._last_url: str = ""
        self._playwright = None
        self._context = None
        self._page = None
        self._profile_dir = None
        self._init_lock = asyncio.Lock()
        self._structured_available = False

    async def initialize(self) -> None:
        async with self._init_lock:
            if self._page is not None or self._structured_available:
                return

            if not HAS_PLAYWRIGHT:
                logger.warning("Playwright unavailable; falling back to system browser mode")
                self._structured_available = False
                return

            executable = _find_browser_executable()
            if not executable:
                logger.warning("No supported browser executable found; falling back to system browser mode")
                self._structured_available = False
                return

            try:
                self._profile_dir = tempfile.mkdtemp(prefix="jarvis-browser-")
                self._playwright = await async_playwright().start()
                browser_type = self._playwright.chromium
                self._context = await browser_type.launch_persistent_context(
                    self._profile_dir,
                    executable_path=executable,
                    headless=self.headless,
                    viewport={"width": 1440, "height": 900},
                    ignore_https_errors=False,
                )
                pages = self._context.pages
                self._page = pages[0] if pages else await self._context.new_page()
                self._structured_available = True
                logger.info(f"Managed browser ready via {executable}")
            except Exception as exc:
                logger.warning(f"Managed browser init failed, using system browser fallback: {exc}")
                self._structured_available = False
                await self.shutdown()

    async def _ensure_page(self):
        await self.initialize()
        if self._page is None and self._context is not None:
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
        return self._page

    async def navigate(self, url: str) -> str:
        try:
            url = _validate_url(url)
        except ValueError as e:
            return f"Navigation blocked: {e}"
        self._last_url = url
        page = await self._ensure_page()
        if page is not None:
            await page.goto(url, wait_until="domcontentloaded")
            return f"Opened in managed browser: {url}"
        logger.info(f"Opening in system browser: {url}")
        webbrowser.open(url)
        return f"Opened in browser: {url}"

    async def search(self, query: str) -> str:
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return await self.navigate(url)

    async def get_content(self) -> str:
        page = await self._ensure_page()
        if page is not None:
            text = await page.locator("body").inner_text()
            return re.sub(r"\s+", " ", text).strip()[:4000] or "(empty page)"
        if not self._last_url:
            return "(no URL has been opened yet)"
        try:
            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 JARVIS/1.0"},
            ) as client:
                r = await client.get(self._last_url)
                r.raise_for_status()
                text = re.sub(r"<[^>]+>", " ", r.text)
                return re.sub(r"\s+", " ", text).strip()[:4000]
        except Exception as e:
            return f"Could not fetch content: {e}"

    async def click(self, selector: str | None = None, text: str | None = None, nth: int = 0) -> str:
        page = await self._ensure_page()
        if page is None:
            return "Browser click unavailable in system-browser fallback."
        locator = self._resolve_locator(page, selector=selector, text=text)
        await locator.nth(max(0, int(nth))).click(timeout=5000)
        await page.wait_for_timeout(350)
        return "Clicked browser element."

    async def fill(
        self,
        selector: str | None = None,
        text: str = "",
        submit: bool = False,
        clear_first: bool = True,
    ) -> str:
        page = await self._ensure_page()
        if page is None:
            return "Browser typing unavailable in system-browser fallback."
        locator = self._resolve_field_locator(page, selector=selector)
        target = locator.first
        await target.click(timeout=5000)
        if clear_first:
            await target.fill("")
        await target.fill(text)
        if submit:
            await page.keyboard.press("Enter")
        await page.wait_for_timeout(250)
        return "Typed in browser field."

    async def press_key(self, key: str) -> str:
        page = await self._ensure_page()
        if page is None:
            return "Browser key press unavailable in system-browser fallback."
        await page.keyboard.press(key)
        await page.wait_for_timeout(250)
        return f"Pressed {key} in browser."

    async def scroll(self, direction: str = "down", amount: int = 600) -> str:
        page = await self._ensure_page()
        if page is None:
            return "Browser scroll unavailable in system-browser fallback."
        delta = max(80, abs(int(amount)))
        if direction.lower() == "up":
            delta = -delta
        elif direction.lower() == "left":
            await page.mouse.wheel(-delta, 0)
            await page.wait_for_timeout(200)
            return f"Scrolled browser {direction}."
        elif direction.lower() == "right":
            await page.mouse.wheel(delta, 0)
            await page.wait_for_timeout(200)
            return f"Scrolled browser {direction}."
        await page.mouse.wheel(0, delta)
        await page.wait_for_timeout(200)
        return f"Scrolled browser {direction}."

    async def wait_for(
        self,
        text: str | None = None,
        selector: str | None = None,
        timeout_ms: int = 5000,
    ) -> str:
        page = await self._ensure_page()
        if page is None:
            return "Browser wait unavailable in system-browser fallback."
        timeout_ms = max(250, min(int(timeout_ms), 20000))
        try:
            if selector:
                await page.wait_for_selector(selector, timeout=timeout_ms)
                return f"Found selector: {selector}"
            if text:
                await page.get_by_text(text).first.wait_for(timeout=timeout_ms)
                return f"Found text: {text}"
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            return "Browser ready."
        except PlaywrightTimeoutError:
            return f"Timed out after {timeout_ms} ms."

    async def list_tabs(self) -> list[dict]:
        page = await self._ensure_page()
        if self._context is None:
            return []
        tabs = []
        for idx, tab in enumerate(self._context.pages):
            tabs.append(
                {
                    "index": idx,
                    "title": await tab.title() if tab else "",
                    "url": tab.url,
                    "active": tab is page,
                }
            )
        return tabs

    async def close_tab(self, index: int = -1) -> str:
        page = await self._ensure_page()
        if self._context is None or not self._context.pages:
            return "No browser tabs to close."
        tabs = self._context.pages
        tab = tabs[index]
        await tab.close()
        remaining = self._context.pages
        self._page = remaining[0] if remaining else None
        return "Closed browser tab."

    async def get_structured_content(self, max_length: int = 6000) -> str:
        page = await self._ensure_page()
        if page is None:
            return "(no structured content available — system browser fallback)"
        try:
            content = await page.evaluate("""() => {
                const r = [];
                r.push('TITLE: ' + document.title);
                r.push('URL: ' + window.location.href);

                document.querySelectorAll('h1,h2,h3').forEach(h => {
                    const t = h.textContent.trim().substring(0, 120);
                    if (t) r.push(h.tagName + ': ' + t);
                });

                const links = [...document.querySelectorAll('a[href]')].slice(0, 20);
                if (links.length) {
                    r.push('\\nLINKS:');
                    links.forEach((a, i) => {
                        const t = a.textContent.trim().substring(0, 60);
                        if (t) r.push('  ' + (i+1) + '. "' + t + '" -> ' + a.href);
                    });
                }

                const inputs = document.querySelectorAll('input, textarea, select');
                if (inputs.length) {
                    r.push('\\nFORM FIELDS:');
                    inputs.forEach(el => {
                        const label = (el.labels && el.labels[0] && el.labels[0].textContent.trim())
                            || el.placeholder || el.name || el.id || '(unlabeled)';
                        r.push('  - ' + el.tagName.toLowerCase() + '[' + (el.type||'text') + ']: "' + label.substring(0,60) + '"');
                    });
                }

                const btns = [...document.querySelectorAll('button, [role="button"]')].slice(0, 15);
                if (btns.length) {
                    r.push('\\nBUTTONS:');
                    btns.forEach((b, i) => {
                        const t = (b.textContent || b.getAttribute('aria-label') || '').trim().substring(0, 60);
                        if (t) r.push('  ' + (i+1) + '. ' + t);
                    });
                }

                const main = document.querySelector('article, main, [role="main"]') || document.body;
                const text = main.innerText.substring(0, 3000);
                r.push('\\nCONTENT:\\n' + text);
                return r.join('\\n');
            }""")
            return str(content)[:max_length]
        except Exception as e:
            return f"Could not extract structured content: {e}"

    async def find_elements(self, query: str, max_results: int = 10) -> list[dict]:
        page = await self._ensure_page()
        if page is None:
            return []
        try:
            return await page.evaluate("""([query, maxResults]) => {
                const q = query.toLowerCase();
                const results = [];
                const seen = new Set();

                function addEl(el, matchText) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) return;
                    const key = el.tagName + ':' + Math.round(rect.x) + ':' + Math.round(rect.y);
                    if (seen.has(key)) return;
                    seen.add(key);
                    results.push({
                        text: matchText.substring(0, 80),
                        tag: el.tagName.toLowerCase(),
                        role: el.getAttribute('role') || el.tagName.toLowerCase(),
                        bounds: {x: Math.round(rect.x), y: Math.round(rect.y),
                                 w: Math.round(rect.width), h: Math.round(rect.height)},
                        selector: el.id ? '#' + el.id : null
                    });
                }

                // ARIA labels
                document.querySelectorAll('[aria-label]').forEach(el => {
                    const label = el.getAttribute('aria-label');
                    if (label.toLowerCase().includes(q)) addEl(el, label);
                });

                // Visible text in interactive elements
                document.querySelectorAll('a, button, [role="button"], input, select, textarea').forEach(el => {
                    const t = (el.textContent || el.value || el.placeholder || '').trim();
                    if (t.toLowerCase().includes(q)) addEl(el, t);
                });

                // Title attributes
                document.querySelectorAll('[title]').forEach(el => {
                    const title = el.getAttribute('title');
                    if (title.toLowerCase().includes(q)) addEl(el, title);
                });

                return results.slice(0, maxResults);
            }""", [query, max_results])
        except Exception as e:
            logger.error(f"find_elements failed: {e}")
            return []

    async def screenshot(self, full_page: bool = False) -> str:
        page = await self._ensure_page()
        if page is None:
            return ""
        screenshot_dir = Path.home() / ".jarvis" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = str(screenshot_dir / f"browser_{int(time.time() * 1000)}.png")
        await page.screenshot(path=path, full_page=full_page)
        logger.info(f"Browser screenshot saved: {path}")
        return path

    async def shutdown(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._page = None
        self._playwright = None
        self._structured_available = False

    @staticmethod
    def _resolve_locator(page, selector: str | None = None, text: str | None = None):
        if selector:
            return page.locator(selector)
        if text:
            return page.get_by_text(text, exact=False)
        return page.locator("a, button, input, textarea, [role='button']")

    @staticmethod
    def _resolve_field_locator(page, selector: str | None = None):
        if selector:
            return page.locator(selector)
        return page.locator("input, textarea, [contenteditable='true'], [role='textbox']")
