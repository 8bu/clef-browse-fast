"""Minimal synchronous CDP client over one browser websocket.

It sends only what the caller asks for and attaches only to targets the caller names. There is no daemon,
no target discovery, and no tab creation: tab lifetime belongs to the Neo MCP adapter.
"""

from __future__ import annotations

import itertools
import json
import threading
import time
from typing import Any

import httpx
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect


class CdpError(RuntimeError):
    """A CDP endpoint or command failed."""


def resolve_ws_url(cdp_url: str, *, timeout_s: float = 3.0) -> str:
    try:
        response = httpx.get(f"{cdp_url.rstrip('/')}/json/version", timeout=timeout_s)
        response.raise_for_status()
        version = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CdpError(f"CDP endpoint is unreachable: {type(exc).__name__}") from exc
    if not isinstance(version, dict) or not str(version.get("Browser", "")).startswith("Chrome/"):
        raise CdpError("CDP endpoint did not identify as Chrome")
    ws_url = version.get("webSocketDebuggerUrl")
    if not isinstance(ws_url, str) or not ws_url.startswith("ws"):
        raise CdpError("CDP endpoint did not return a websocket URL")
    return ws_url


class CdpConnection:
    def __init__(self, ws_url: str, *, timeout_s: float = 30.0) -> None:
        self.timeout_s = timeout_s
        self.closed = False
        try:
            self._ws = connect(ws_url, max_size=32 * 1024 * 1024, compression=None, open_timeout=5)
        except (OSError, TimeoutError) as exc:
            raise CdpError(f"CDP websocket connection failed: {type(exc).__name__}") from exc
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def call(self, method: str, session_id: str | None = None, **params: Any) -> dict:
        with self._lock:
            if self.closed:
                raise CdpError("CDP connection is closed")
            message_id = next(self._ids)
            payload: dict[str, Any] = {"id": message_id, "method": method, "params": params}
            if session_id:
                payload["sessionId"] = session_id
            deadline = time.monotonic() + self.timeout_s
            try:
                self._ws.send(json.dumps(payload))
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise CdpError(f"{method} timed out")
                    try:
                        message = json.loads(self._ws.recv(timeout=remaining))
                    except TimeoutError:
                        raise CdpError(f"{method} timed out") from None
                    if message.get("id") != message_id:
                        continue
                    if "error" in message:
                        detail = (
                            message["error"].get("message", "error") if isinstance(message["error"], dict) else "error"
                        )
                        raise CdpError(f"{method}: {detail}")
                    return message.get("result", {})
            except (ConnectionClosed, OSError) as exc:
                self.closed = True
                raise CdpError(f"CDP connection lost during {method}") from exc

    def close(self) -> None:
        self.closed = True
        self._ws.close()


_shared: dict[str, CdpConnection] = {}
_shared_lock = threading.Lock()


def shared_connection(cdp_url: str) -> CdpConnection:
    """One reusable connection per endpoint; a dropped connection is replaced on the next run."""
    with _shared_lock:
        connection = _shared.get(cdp_url)
        if connection is None or connection.closed:
            connection = CdpConnection(resolve_ws_url(cdp_url))
            _shared[cdp_url] = connection
        return connection
