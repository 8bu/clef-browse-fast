import json

import httpx
import pytest

from clef_browse.neo import NeoError, NeoMcp, NeoTab, close_tab, is_risky, open_tab


def rpc_result(result, *, session_id="session-1"):
    return httpx.Response(
        200,
        headers={"content-type": "application/json", "mcp-session-id": session_id},
        json={"jsonrpc": "2.0", "id": 1, "result": result},
    )


def tool_response(text, *, session_id="session-1", sse=False):
    result = {"content": [{"type": "text", "text": text}]}
    if sse:
        body = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': 3, 'result': result})}\n\n"
        return httpx.Response(
            200, headers={"content-type": "text/event-stream", "mcp-session-id": session_id}, text=body
        )
    return rpc_result(result, session_id=session_id)


def run_output(value):
    return f'ok\nreturn: {json.dumps(value, indent=2)}Tip: this session is "a/b" — rename it with name_session'


def page_info(ownership, target="target-7"):
    return run_output({"targetId": target, "ownership": ownership})


def test_sse_data_lines_and_session_id_reuse():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((body, request.headers.get("mcp-session-id")))
        if body["method"] == "initialize":
            return rpc_result({"protocolVersion": "2025-06-18"})
        if body["method"] == "notifications/initialized":
            return httpx.Response(202, headers={"mcp-session-id": "session-1"})
        return tool_response("run result", sse=True)

    mcp = NeoMcp("http://neo/mcp", transport=httpx.MockTransport(handler))
    assert mcp.call_tool("run", {"code": "return 1"}) == "run result"
    assert mcp.call_tool("run", {"code": "return 2"}) == "run result"
    assert calls[2][1] == "session-1"
    assert calls[3][1] == "session-1"
    mcp.close()


def test_open_tab_reads_target_and_ownership_in_a_single_run_call():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if body["method"] == "initialize":
            return rpc_result({})
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        if body["params"]["name"] == "tabs":
            return tool_response('opened page 42Tip: this session is "a/b"')
        return tool_response(page_info("mine", "target-42"))

    mcp = NeoMcp("http://neo/mcp", transport=httpx.MockTransport(handler))
    tab = open_tab(mcp, "https://example.test")
    assert tab == NeoTab(42, "target-42", "https://example.test")
    assert (42, "target-42") in mcp._owned_tabs
    assert [c["params"]["name"] for c in calls if c["method"] == "tools/call"] == ["tabs", "run"]
    mcp.close()


class RecordingMcp:
    def __init__(self, tabs_reply, run_reply):
        self._owned_tabs = set()
        self.calls = []
        self.tabs_reply, self.run_reply = tabs_reply, run_reply

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "tabs":
            return self.tabs_reply if arguments["action"] == "new" else f"closed page {arguments['page']}"
        return self.run_reply

    def closed_pages(self):
        return [a["page"] for n, a in self.calls if n == "tabs" and a["action"] == "close"]


@pytest.mark.parametrize("ownership", ["user", "other-agent", None])
def test_open_tab_refuses_page_not_owned_and_never_closes_it(ownership):
    mcp = RecordingMcp("opened page 9", page_info(ownership, "target-9"))
    with pytest.raises(NeoError, match="not owned"):
        open_tab(mcp, "https://example.test")
    assert mcp.closed_pages() == []
    assert not mcp._owned_tabs


@pytest.mark.parametrize("run_reply", ["garbage", "ok\nreturn: {not json", run_output({"ownership": "mine"})])
def test_open_tab_closes_the_page_it_just_opened_when_run_output_is_unusable(run_reply):
    mcp = RecordingMcp("opened page 5", run_reply)
    with pytest.raises(NeoError):
        open_tab(mcp, "https://example.test")
    assert mcp.closed_pages() == [5]
    assert not mcp._owned_tabs


def test_close_tab_refuses_non_mine_without_closing():
    mcp = RecordingMcp("", page_info("other-agent"))
    mcp._owned_tabs = {(7, "target-7")}
    with pytest.raises(NeoError, match="not owned"):
        close_tab(mcp, NeoTab(7, "target-7", "https://example.test"))
    assert mcp.closed_pages() == []


def test_close_tab_closes_only_the_tab_this_adapter_opened():
    mcp = RecordingMcp("opened page 7", page_info("mine"))
    tab = open_tab(mcp, "https://example.test")
    assert tab == NeoTab(7, "target-7", "https://example.test")
    close_tab(mcp, tab)
    assert mcp.closed_pages() == [7]
    with pytest.raises(NeoError, match="not opened"):
        close_tab(mcp, tab)
    with pytest.raises(NeoError, match="not opened"):
        close_tab(mcp, NeoTab(8, "target-8", "https://example.test"))
    assert mcp.closed_pages() == [7]


def test_target_attached_browser_never_creates_or_closes_target():
    import jev_ultrafast.browser as browser_module

    calls = []

    def fake_cdp(method, **kwargs):
        calls.append((method, kwargs))
        if method == "Target.attachToTarget":
            return {"sessionId": "session-1"}
        if method == "Runtime.evaluate":
            return {"result": {"value": "complete"}}
        return {}

    browser = browser_module.Browser("https://example.test", target_id="existing-target", cdp=fake_cdp)
    browser.close()
    methods = [method for method, _ in calls]
    assert "Target.createTarget" not in methods
    assert "Target.closeTarget" not in methods
    assert ("Target.attachToTarget", {"targetId": "existing-target", "flatten": True}) in calls
    assert ("Target.detachFromTarget", {"sessionId": "session-1"}) in calls


@pytest.mark.parametrize("term", ["submit", "purchase", "delete", "send", "pay"])
def test_risky_action_terms_are_case_insensitive(term):
    assert is_risky(f"Please {term.upper()} now", "button", "click") == term


@pytest.mark.parametrize("label", ["Post", "POST", "Post reply", "  post note"])
def test_post_is_risky_at_the_start_of_a_label(label):
    assert is_risky(label, "button", "click") == "post"


@pytest.mark.parametrize("label", ["New post", "Posts", "Payment details", "Postgres settings", "Resubmit"])
def test_risky_terms_match_whole_words_only(label):
    assert is_risky(label, "link", "click") is None


@pytest.mark.parametrize("kind", ["select", "fill"])
def test_select_and_fill_are_not_risky_by_label_alone(kind):
    assert is_risky("Submit payment", "button", kind) is None
