from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any

import httpx

from ._version import __version__


class NeoError(RuntimeError):
    """A BrowserOS Neo request or ownership check failed."""


@dataclass
class NeoMcp:
    url: str
    transport: httpx.BaseTransport | None = field(default=None, kw_only=True)
    timeout_s: float = field(default=15.0, kw_only=True)
    _client: httpx.Client = field(init=False, repr=False)
    _session_id: str | None = field(default=None, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)
    _owned_tabs: set[tuple[int, str]] = field(default_factory=set, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(timeout=self.timeout_s, transport=self.transport)

    def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        notification: bool = False,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notification:
            self._request_id += 1
            payload["id"] = self._request_id
        if params is not None:
            payload["params"] = params
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        try:
            response = self._client.post(self.url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NeoError(f"Neo MCP request failed: {exc}") from exc
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        if notification and not response.content:
            return None
        try:
            if "text/event-stream" in response.headers.get("content-type", ""):
                messages = [
                    json.loads(line[5:].strip())
                    for line in response.text.splitlines()
                    if line.startswith("data:") and line[5:].strip()
                ]
                if not messages:
                    raise ValueError("SSE response has no data message")
                message = messages[-1]
            else:
                message = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise NeoError("Neo MCP returned invalid JSON/SSE") from exc
        if not isinstance(message, dict):
            raise NeoError("Neo MCP returned a non-object response")
        if "error" in message:
            raise NeoError(f"Neo MCP JSON-RPC error: {message['error']}")
        return message

    def _initialize(self) -> None:
        if self._initialized:
            return
        self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "clef-browse-fast", "version": __version__},
            },
        )
        self._request("notifications/initialized", notification=True)
        self._initialized = True

    def call_tool(self, name: str, arguments: dict) -> str:
        if name not in {"tabs", "run"}:
            raise NeoError(f"Unsupported Neo tool: {name}")
        with self._lock:
            self._initialize()
            response = self._request("tools/call", {"name": name, "arguments": arguments})
        result = response.get("result") if response else None
        if not isinstance(result, dict):
            raise NeoError("Neo MCP tool response is missing result")
        if result.get("isError"):
            raise NeoError("Neo MCP tool reported an error")
        content = result.get("content", [])
        return "".join(
            item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"
        )

    def close(self) -> None:
        self._client.close()


@dataclass(frozen=True)
class NeoTab:
    page_id: int
    target_id: str
    url: str


def _run_value(mcp: NeoMcp, code: str) -> Any:
    output = mcp.call_tool("run", {"code": code})
    _, marker, rest = output.partition("return: ")
    if not output.startswith("ok") or not marker:
        raise NeoError("Neo run tool did not return a value")
    try:
        value, _ = json.JSONDecoder().raw_decode(rest)
    except json.JSONDecodeError as exc:
        raise NeoError("Neo run tool returned invalid JSON") from exc
    return value


def _page_info(mcp: NeoMcp, page_id: int) -> dict | None:
    code = (
        f"const p = (await browser.pages.list()).find(p => p.pageId === {int(page_id)}); "
        "return p ? {targetId: p.targetId, ownership: p.ownership} : null"
    )
    info = _run_value(mcp, code)
    return info if isinstance(info, dict) else None


def _release(mcp: NeoMcp, page_id: int) -> None:
    try:
        mcp.call_tool("tabs", {"action": "close", "page": page_id})
    except NeoError:
        pass


def open_tab(mcp: NeoMcp, url: str) -> NeoTab:
    output = mcp.call_tool("tabs", {"action": "new", "url": url})
    match = re.search(r"opened page (\d+)", output)
    if not match:
        raise NeoError("Neo tabs tool did not return an opened page id")
    page_id = int(match.group(1))
    try:
        info = _page_info(mcp, page_id)
    except NeoError:
        _release(mcp, page_id)
        raise
    if not info or info.get("ownership") != "mine":
        raise NeoError(f"Neo page {page_id} is not owned by this session")
    target_id = info.get("targetId")
    if not isinstance(target_id, str) or not target_id:
        _release(mcp, page_id)
        raise NeoError("Neo did not return a target id")
    tab = NeoTab(page_id=page_id, target_id=target_id, url=url)
    mcp._owned_tabs.add((tab.page_id, tab.target_id))
    return tab


def close_tab(mcp: NeoMcp, tab: NeoTab) -> None:
    key = (tab.page_id, tab.target_id)
    if key not in mcp._owned_tabs:
        raise NeoError("Refusing to close a tab not opened by this adapter")
    info = _page_info(mcp, tab.page_id)
    if not info or info.get("ownership") != "mine":
        raise NeoError("Refusing to close a page not owned by this session")
    mcp.call_tool("tabs", {"action": "close", "page": tab.page_id})
    mcp._owned_tabs.remove(key)


class NeoLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def acquire(self) -> None:
        self._lock.acquire()

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> NeoLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.release()


RISKY_TERMS = (
    "submit",
    "purchase",
    "delete",
    "send",
    "pay",
    "confirm",
    "publish",
    "place order",
    "remove",
    "sign out",
)
# "post" is risky only at the start of a label ("Post", "Post reply"). "New post" only opens an editor.
RISKY_LEADING_TERMS = ("post",)


def is_risky(label: str, role: str | None, action_kind: str) -> str | None:
    if action_kind not in {"click", "press-enter"}:
        return None
    text = f"{label} {role or ''}".casefold()
    for term in RISKY_TERMS:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text):
            return term
    for term in RISKY_LEADING_TERMS:
        if re.match(rf"\s*{re.escape(term)}(?!\w)", label.casefold()):
            return term
    return None
