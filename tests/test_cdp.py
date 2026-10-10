import json
import socket
import threading
from contextlib import closing

import pytest
from websockets.sync.server import serve

from clef_browse import cdp
from clef_browse.cdp import CdpConnection, CdpError, resolve_ws_url


@pytest.fixture
def ws_server():
    servers = []

    def start(handler):
        server = serve(handler, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"ws://127.0.0.1:{server.socket.getsockname()[1]}"

    yield start
    for server in servers:
        server.shutdown()


def noisy_echo(connection):
    for raw in connection:
        request = json.loads(raw)
        connection.send(json.dumps({"method": "Page.loadEventFired", "params": {}}))
        connection.send(json.dumps({"id": 9999, "result": {"stale": True}}))
        if request["method"] == "Bad.method":
            connection.send(json.dumps({"id": request["id"], "error": {"code": -32601, "message": "not found"}}))
            continue
        result = {"method": request["method"], "params": request["params"], "sessionId": request.get("sessionId")}
        connection.send(json.dumps({"id": request["id"], "result": result}))


def test_call_returns_matching_response_and_skips_events_and_stale_ids(ws_server):
    connection = CdpConnection(ws_server(noisy_echo))
    try:
        result = connection.call("Runtime.evaluate", session_id="s1", expression="1+1")
        assert result == {"method": "Runtime.evaluate", "params": {"expression": "1+1"}, "sessionId": "s1"}
        assert connection.call("Browser.getVersion")["sessionId"] is None
    finally:
        connection.close()


def test_cdp_error_response_raises_with_method_and_message(ws_server):
    connection = CdpConnection(ws_server(noisy_echo))
    try:
        with pytest.raises(CdpError, match="Bad.method: not found"):
            connection.call("Bad.method")
        assert not connection.closed
        assert connection.call("Browser.getVersion")["method"] == "Browser.getVersion"
    finally:
        connection.close()


def test_unanswered_call_times_out_without_closing_connection(ws_server):
    def silent(connection):
        for _ in connection:
            pass

    connection = CdpConnection(ws_server(silent), timeout_s=0.3)
    try:
        with pytest.raises(CdpError, match="timed out"):
            connection.call("Page.enable")
        assert not connection.closed
    finally:
        connection.close()


def test_dropped_connection_marks_closed_and_shared_connection_replaces_it(ws_server, monkeypatch):
    def drop_first_then_echo(connection):
        connection.recv()
        connection.close()

    dropping = ws_server(drop_first_then_echo)
    healthy = ws_server(noisy_echo)
    urls = iter([dropping, healthy])
    monkeypatch.setattr(cdp, "resolve_ws_url", lambda _url: next(urls))
    monkeypatch.setattr(cdp, "_shared", {})

    first = cdp.shared_connection("http://neo")
    with pytest.raises(CdpError, match="lost|closed"):
        first.call("Page.enable")
    assert first.closed
    with pytest.raises(CdpError, match="closed"):
        first.call("Page.enable")

    second = cdp.shared_connection("http://neo")
    try:
        assert second is not first
        assert second.call("Browser.getVersion")["method"] == "Browser.getVersion"
        assert cdp.shared_connection("http://neo") is second
    finally:
        second.close()


def test_resolve_ws_url_requires_chrome_and_websocket_url(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    monkeypatch.setattr(
        cdp.httpx,
        "get",
        lambda url, timeout: Response({"Browser": "Chrome/155.0", "webSocketDebuggerUrl": "ws://127.0.0.1:9/devtools"}),
    )
    assert resolve_ws_url("http://neo/") == "ws://127.0.0.1:9/devtools"

    monkeypatch.setattr(cdp.httpx, "get", lambda url, timeout: Response({"Browser": "Firefox/1"}))
    with pytest.raises(CdpError, match="Chrome"):
        resolve_ws_url("http://neo")

    monkeypatch.setattr(cdp.httpx, "get", lambda url, timeout: Response({"Browser": "Chrome/1"}))
    with pytest.raises(CdpError, match="websocket"):
        resolve_ws_url("http://neo")


def test_resolve_ws_url_reports_unreachable_endpoint():
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(CdpError, match="unreachable"):
        resolve_ws_url(f"http://127.0.0.1:{port}")
