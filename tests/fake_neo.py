from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

from websockets.sync.client import connect


class FakeNeo:
    def __init__(self, cdp_url: str):
        self.cdp_url = cdp_url.rstrip("/")
        self.pages: dict[int, str] = {}
        self.closed_pages: dict[int, dict] = {}
        self._next_page_id = 1
        self._lock = threading.Lock()
        self._session_id = "fake-neo-session"
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                method = request.get("method")
                if method == "notifications/initialized":
                    self.send_response(202)
                    self.end_headers()
                    return
                if method == "initialize":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("mcp-session-id", owner._session_id)
                    self.end_headers()
                    self.wfile.write(
                        owner._sse(
                            request.get("id"),
                            {
                                "protocolVersion": "2025-06-18",
                                "capabilities": {"tools": {}},
                                "serverInfo": {"name": "fake-neo", "version": "1"},
                            },
                        )
                    )
                    return
                if self.headers.get("mcp-session-id") != owner._session_id:
                    self._reply(request.get("id"), error={"code": -32000, "message": "Invalid session"})
                    return
                if method != "tools/call":
                    self._reply(request.get("id"), error={"code": -32601, "message": "Unsupported method"})
                    return
                params = request.get("params", {})
                try:
                    value = owner._call(params.get("name"), params.get("arguments", {}))
                    self._reply(request.get("id"), result={"content": [{"type": "text", "text": value}]})
                except Exception as exc:
                    self._reply(request.get("id"), error={"code": -32000, "message": str(exc)})

            def _reply(self, request_id, *, result=None, error=None):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                body = {"jsonrpc": "2.0", "id": request_id}
                body["result" if error is None else "error"] = result if error is None else error
                self.wfile.write(b"data: " + json.dumps(body).encode() + b"\n\n")

            def log_message(self, _format, *_args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{self._server.server_port}/mcp"

    @staticmethod
    def _sse(request_id, result) -> bytes:
        payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
        return b"data: " + json.dumps(payload).encode() + b"\n\n"

    def _target_command(self, target_id: str, method: str, **params):
        with urlopen(f"{self.cdp_url}/json/list", timeout=5) as response:
            targets = json.load(response)
        endpoint = next(
            (target.get("webSocketDebuggerUrl") for target in targets if target.get("id") == target_id), None
        )
        if endpoint is None:
            raise ValueError("Unknown target")
        with connect(endpoint, open_timeout=5) as ws:
            ws.send(json.dumps({"id": 1, "method": method, "params": params}))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == 1:
                    if "error" in message:
                        raise RuntimeError(message["error"].get("message", "CDP command failed"))
                    return message.get("result", {})

    def _cdp(self, method: str, **params):
        with urlopen(f"{self.cdp_url}/json/version", timeout=5) as response:
            endpoint = json.load(response)["webSocketDebuggerUrl"]
        with connect(endpoint, open_timeout=5) as ws:
            ws.send(json.dumps({"id": 1, "method": method, "params": params}))
            while True:
                message = json.loads(ws.recv())
                if message.get("id") == 1:
                    if "error" in message:
                        raise RuntimeError(message["error"].get("message", "CDP command failed"))
                    return message.get("result", {})

    def _call(self, name: str, arguments: dict) -> str:
        if name == "tabs":
            action = arguments.get("action")
            if action == "new":
                target_id = self._cdp("Target.createTarget", url=arguments["url"])["targetId"]
                with self._lock:
                    page_id = self._next_page_id
                    self._next_page_id += 1
                    self.pages[page_id] = target_id
                return f"opened page {page_id}"
            if action == "close":
                page_id = int(arguments["page"])
                with self._lock:
                    target_id = self.pages.pop(page_id, None)
                if target_id is None:
                    raise ValueError("Unknown fake Neo page")
                state = (
                    self._target_command(
                        target_id,
                        "Runtime.evaluate",
                        expression=(
                            "JSON.stringify({url: location.href, title: document.title, "
                            "status: document.querySelector('#status')?.textContent ?? null})"
                        ),
                        returnByValue=True,
                    )
                    .get("result", {})
                    .get("value")
                )
                with self._lock:
                    self.closed_pages[page_id] = json.loads(state) if state else {}
                self._cdp("Target.closeTarget", targetId=target_id)
                return f"closed page {page_id}"
            raise ValueError("Unsupported tabs action")
        if name != "run":
            raise ValueError("Unsupported tool")
        code = arguments.get("code", "")
        match = re.search(r"p\.pageId === (\d+)", code)
        if "pages.list()" not in code or not match:
            raise ValueError("Unsupported run expression")
        page_id = int(match.group(1))
        with self._lock:
            target_id = self.pages.get(page_id)
        info = {"targetId": target_id, "ownership": "mine"} if target_id else None
        return f'ok\nreturn: {json.dumps(info, indent=2)}Tip: this session is "fake/neo" — rename it'

    def close(self):
        with self._lock:
            pages = list(self.pages.items())
            self.pages.clear()
        for _, target_id in pages:
            try:
                self._cdp("Target.closeTarget", targetId=target_id)
            except Exception:
                pass
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
