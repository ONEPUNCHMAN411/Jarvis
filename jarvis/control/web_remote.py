
import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from loguru import logger

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>JARVIS Remote</title>
<style>
  :root { --bg:#070b14; --panel:#0e1422; --line:rgba(148,163,184,.14);
          --blue:#3b9eff; --text:#dfe5f0; --muted:#7c879d; }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
         display:flex; flex-direction:column; height:100vh; }
  header { padding:14px 18px; border-bottom:1px solid var(--line);
           display:flex; align-items:center; gap:10px; }
  header .dot { width:9px; height:9px; border-radius:50%; background:var(--blue);
                box-shadow:0 0 10px var(--blue); }
  header b { letter-spacing:3px; font-size:15px; }
  header span { color:var(--muted); font-size:11px; margin-left:auto; }
  #log { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:10px; }
  .msg { max-width:84%; padding:10px 13px; border-radius:14px; font-size:15px;
         line-height:1.4; white-space:pre-wrap; word-wrap:break-word; }
  .you { align-self:flex-end; background:var(--blue); color:#04121f; border-bottom-right-radius:4px; }
  .jarvis { align-self:flex-start; background:var(--panel); border:1px solid var(--line);
            border-bottom-left-radius:4px; }
  .meta { font-size:11px; color:var(--muted); align-self:flex-start; }
  form { display:flex; gap:8px; padding:12px; border-top:1px solid var(--line); }
  input { flex:1; background:var(--panel); border:1px solid var(--line); color:var(--text);
          border-radius:12px; padding:13px 14px; font-size:16px; outline:none; }
  input:focus { border-color:var(--blue); }
  button { background:var(--blue); color:#04121f; border:none; border-radius:12px;
           padding:0 20px; font-size:16px; font-weight:700; }
  button:disabled { opacity:.5; }
</style>
</head>
<body>
  <header><span class="dot"></span><b>JARVIS</b><span>remote</span></header>
  <div id="log"></div>
  <form id="f">
    <input id="t" placeholder="Tell JARVIS what to do..." autocomplete="off" autofocus>
    <button id="b" type="submit">Send</button>
  </form>
<script>
  const log = document.getElementById('log');
  const form = document.getElementById('f');
  const input = document.getElementById('t');
  const btn = document.getElementById('b');
  function add(text, cls) {
    const d = document.createElement('div');
    d.className = 'msg ' + cls;
    d.textContent = text;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    add(text, 'you');
    btn.disabled = true;
    const thinking = add('thinking...', 'meta');
    try {
      const r = await fetch('/api/send', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({text})
      });
      const j = await r.json();
      thinking.remove();
      add(j.response || j.error || '(no response)', 'jarvis');
    } catch (err) {
      thinking.remove();
      add('Connection error: ' + err, 'jarvis');
    } finally {
      btn.disabled = false;
      input.focus();
    }
  });
</script>
</body>
</html>"""


def _lan_ip() -> str:
    """Best-effort local network IP (the address phones should connect to)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class _Bridge:
    """Sends text through the normal assistant pipeline and awaits the reply
    by listening for the next AIResponseEvent on the runtime event bus."""

    def __init__(self, runtime):
        self.runtime = runtime
        self._pending = None
        self._lock = asyncio.Lock()
        self._subscribed = False

    def _on_response(self, event) -> None:
        if self._pending is not None and not self._pending.done():
            self._pending.set_result(getattr(event, "text", "") or "")

    async def ask(self, text: str, timeout: float = 120.0) -> str:
        from jarvis.models import AIResponseEvent
        if not self._subscribed:
            self.runtime.async_runtime.bus.subscribe(AIResponseEvent, self._on_response)
            self._subscribed = True
        async with self._lock:
            loop = asyncio.get_running_loop()
            self._pending = loop.create_future()
            try:
                self.runtime.send_text(text)
                return await asyncio.wait_for(self._pending, timeout)
            except asyncio.TimeoutError:
                return "(JARVIS took too long to respond)"
            finally:
                self._pending = None


class WebRemoteServer:
    def __init__(self, port: int = 8765):
        self.port = port
        self._httpd = None
        self._thread = None
        self._bridge = None

    def is_running(self) -> bool:
        return self._httpd is not None

    def url(self) -> str:
        return f"http://{_lan_ip()}:{self.port}"

    def start(self) -> bool:
        if self._httpd is not None:
            return True
        from jarvis.app import get_runtime
        runtime = get_runtime()
        if runtime is None or runtime.async_runtime.loop is None:
            return False
        self._bridge = _Bridge(runtime)
        loop = runtime.async_runtime.loop
        bridge = self._bridge
        page = _PAGE.encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, code, body, ctype="application/json; charset=utf-8"):
                data = body if isinstance(body, bytes) else body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except Exception:
                    pass

            def do_GET(self):
                if self.path == "/" or self.path.startswith("/?"):
                    self._reply(200, page, "text/html; charset=utf-8")
                elif self.path == "/api/status":
                    self._reply(200, json.dumps({"ok": True}))
                else:
                    self._reply(404, json.dumps({"error": "not found"}))

            def do_POST(self):
                if self.path != "/api/send":
                    self._reply(404, json.dumps({"error": "not found"}))
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(length) if length else b"{}"
                    text = (json.loads(raw.decode("utf-8")).get("text") or "").strip()
                except Exception:
                    text = ""
                if not text:
                    self._reply(400, json.dumps({"error": "empty message"}))
                    return
                try:
                    fut = asyncio.run_coroutine_threadsafe(bridge.ask(text), loop)
                    reply = fut.result(timeout=125)
                except Exception as e:
                    reply = f"Error: {e}"
                self._reply(200, json.dumps({"response": reply}))

        try:
            self._httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        except OSError as e:
            logger.warning(f"Web remote could not bind port {self.port}: {e}")
            self._httpd = None
            return False
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="JarvisWebRemote"
        )
        self._thread.start()
        logger.info(f"Web remote serving at {self.url()}")
        return True

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
            self._thread = None


_instance: "WebRemoteServer | None" = None


def get_web_remote_server() -> "WebRemoteServer":
    global _instance
    if _instance is None:
        _instance = WebRemoteServer()
    return _instance
