import sys
import types

from clef_browse import executor
from clef_browse.config import RunLimits


class StubMcp:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def call_tool(self, name, arguments):
        return ""


class FakeBrowser:
    instances = []

    def __init__(self, url, *, target_id=None, cdp=None):
        self.url = url
        self.acted = []
        self.closed = False
        self.instances.append(self)

    def observe(self, **kwargs):
        return {
            "url": self.url,
            "title": "Demo",
            "text": "",
            "actions": [{"id": "a1", "kind": "click", "label": "Submit order", "role": "button"}],
        }

    def act(self, action, page, **kwargs):
        self.acted.append(action)

    def close(self):
        self.closed = True

    def call(self, method, **params):
        return {}


class FakeAgent:
    def __init__(self, goal, *, browser, decide):
        self.browser, self.decide = browser, decide
        self.state = {"history": [], "page": None, "status": "ready"}

    def run(self):
        self.state["page"] = self.browser.observe()
        self.decide(self.state["page"], "goal", [])
        action = self.state["page"]["actions"][0]
        self.browser.act(action, self.state["page"])
        self.state["history"].append({"action": action["label"]})
        self.state["status"] = "done"
        yield self.state


def patch_runtime(monkeypatch, agent_type=FakeAgent):
    monkeypatch.setattr(executor, "shared_connection", lambda url: types.SimpleNamespace(call=lambda *a, **k: {}))
    monkeypatch.setattr(
        executor, "open_tab", lambda mcp, url: types.SimpleNamespace(page_id=7, target_id="target", url=url)
    )
    monkeypatch.setattr(executor, "close_tab", lambda mcp, tab: None)
    browser_mod = types.ModuleType("jev_ultrafast.browser")
    browser_mod.Browser = FakeBrowser
    agent_mod = types.ModuleType("jev_ultrafast.agent")
    agent_mod.Agent = agent_type
    monkeypatch.setitem(sys.modules, "jev_ultrafast.browser", browser_mod)
    monkeypatch.setitem(sys.modules, "jev_ultrafast.agent", agent_mod)
    from clef_browse.clef import cost_usd

    clef_mod = types.ModuleType("clef_browse.clef")
    clef_mod.make_decider = lambda: lambda *args: {}
    clef_mod.cost_usd = cost_usd
    monkeypatch.setitem(sys.modules, "clef_browse.clef", clef_mod)


def test_result_shape_and_risky_action_is_not_executed(monkeypatch):
    patch_runtime(monkeypatch)
    FakeBrowser.instances.clear()

    def decide(*args):
        return {"choice": "a1", "operation": "CLICK", "_meta": {"input_tokens": 12, "output_tokens": 2}}

    result = executor.run_task("http://example.test", "goal", decide=decide, mcp=StubMcp())
    assert result["status"] == "needs_approval"
    assert FakeBrowser.instances[-1].acted == []
    assert result["steps"] == 0
    assert set(result) == {
        "status",
        "outcome",
        "error",
        "risky",
        "steps",
        "model_calls",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "timing_ms",
        "tab",
        "page",
    }


class SubmitTwiceAgent:
    def __init__(self, goal, *, browser, decide):
        self.browser, self.decide = browser, decide
        self.state = {"history": [], "page": None, "status": "ready"}

    def run(self):
        page = self.state["page"] = self.browser.observe()
        for _ in range(2):
            self.decide(page, "goal", self.state["history"])
            self.browser.act(page["actions"][0], page)
            self.state["history"].append({"action": "Submit order"})
        self.state["status"] = "done"
        yield self.state


def test_approval_covers_a_risky_action_once_per_run(monkeypatch):
    patch_runtime(monkeypatch, SubmitTwiceAgent)
    FakeBrowser.instances.clear()
    result = executor.run_task(
        "http://example.test",
        "goal",
        allow_risky_actions=True,
        decide=lambda *args: {"choice": "a1", "operation": "CLICK"},
        mcp=StubMcp(),
    )
    assert result["status"] == "needs_approval"
    assert result["risky"] == {"label": "Submit order", "reason": "submit"}
    assert len(FakeBrowser.instances[-1].acted) == 1
    assert result["steps"] == 1


def test_limit_enforcement_and_close_tab_finally(monkeypatch):
    patch_runtime(monkeypatch)
    closed = []
    monkeypatch.setattr(executor, "close_tab", lambda mcp, tab: closed.append(tab.page_id))
    result = executor.run_task(
        "http://example.test",
        "goal",
        limits=RunLimits(max_steps=0),
        decide=lambda *args: {"choice": "DONE"},
        mcp=StubMcp(),
    )
    assert result["status"] == "limit"
    assert closed == [7]


def test_close_tab_runs_when_agent_raises(monkeypatch):
    class BrokenAgent:
        def __init__(self, goal, *, browser, decide):
            self.state = {"history": [], "page": None}
            self.browser = browser

        def run(self):
            raise RuntimeError("failure")

    patch_runtime(monkeypatch, BrokenAgent)
    closed = []
    monkeypatch.setattr(executor, "close_tab", lambda mcp, tab: closed.append(tab.page_id))
    result = executor.run_task("http://example.test", "goal", mcp=StubMcp())
    assert result["status"] == "error"
    assert closed == [7]


def test_missing_clef_credentials_fail_before_any_tab_is_opened(monkeypatch):
    import clef_browse.clef as clef

    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(clef, "_SHARED_CLIENT", None)
    opened = []
    monkeypatch.setattr(executor, "shared_connection", lambda url: types.SimpleNamespace(call=lambda *a, **k: {}))
    monkeypatch.setattr(executor, "open_tab", lambda mcp, url: opened.append(url))
    result = executor.run_task("http://example.test", "goal", mcp=StubMcp())
    assert result["status"] == "error"
    assert "CLOUDFLARE" in result["error"]
    assert opened == []
    assert result["tab"] is None
