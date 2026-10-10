import logging
import time
from typing import Callable

from .cdp import shared_connection
from .config import RunLimits, neo_urls
from .neo import NeoLock, NeoMcp, close_tab, is_risky, open_tab
from .settle import wait_until_settled


class ApprovalRequired(RuntimeError):
    def __init__(self, decision: dict, element_label: str, reason: str):
        super().__init__(reason)
        self.decision = decision
        self.element_label = element_label
        self.reason = reason


class _RunLimit(RuntimeError):
    pass


class _NoTarget(RuntimeError):
    pass


class _LockedBrowser:
    def __init__(self, browser, lock: NeoLock):
        self._browser = browser
        self._lock = lock
        self.browser_total = 0.0

    def observe(self, *args, **kwargs):
        began = time.perf_counter()
        try:
            return self._browser.observe(*args, **kwargs)
        finally:
            self.browser_total += time.perf_counter() - began

    def act(self, *args, **kwargs):
        began = time.perf_counter()
        self._lock.acquire()
        try:
            return self._browser.act(*args, **kwargs)
        finally:
            self._lock.release()
            self.browser_total += time.perf_counter() - began

    def __getattr__(self, name):
        return getattr(self._browser, name)


def _result(
    status: str,
    *,
    error=None,
    risky=None,
    steps=0,
    model_calls=0,
    input_tokens=0,
    output_tokens=0,
    cost=0.0,
    timing=None,
    tab=None,
    page=None,
) -> dict:
    return {
        "status": status,
        "outcome": status if status in {"done", "blocked"} else None,
        "error": error,
        "risky": risky,
        "steps": steps,
        "model_calls": model_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
        "timing_ms": timing
        or {"total": 0.0, "attach": 0.0, "decide_total": 0.0, "browser_total": 0.0, "decide_mean": 0.0},
        "tab": tab,
        "page": page,
    }


def run_task(
    url: str,
    goal: str,
    *,
    allow_risky_actions: bool = False,
    limits: RunLimits | None = None,
    decide: Callable | None = None,
    mcp: NeoMcp | None = None,
) -> dict:
    limits = limits or RunLimits.from_env()
    mcp_url, cdp_url = neo_urls()
    owned_mcp = mcp is None
    if mcp is None:
        mcp = NeoMcp(mcp_url)
    started = time.perf_counter()
    attach_s = 0.0
    decide_total = 0.0
    model_calls = input_tokens = output_tokens = 0
    cost = 0.0
    tab = None
    raw_browser = None
    agent = browser = None
    risky = None
    approved_risky: set[tuple[str, str]] = set()
    status, error = "error", None
    try:
        from jev_ultrafast.agent import Agent
        from jev_ultrafast.browser import Browser

        from .clef import cost_usd, make_decider

        base_decide = decide if decide is not None else make_decider()
        attach_started = time.perf_counter()
        connection = shared_connection(cdp_url)
        tab = open_tab(mcp, url)
        raw_browser = Browser(url, target_id=tab.target_id, cdp=connection.call)
        wait_until_settled(raw_browser, limits.settle_ms)
        attach_s = time.perf_counter() - attach_started

        def checked_decide(state, task_goal, history):
            nonlocal model_calls, input_tokens, output_tokens, decide_total, cost
            if model_calls >= limits.max_model_calls:
                raise _RunLimit("Maximum model calls reached")
            if time.perf_counter() - started >= limits.timeout_s:
                raise _RunLimit("Run timed out")
            if len(history) >= limits.max_steps:
                raise _RunLimit("Maximum steps reached")
            began = time.perf_counter()
            model_calls += 1
            try:
                choice = base_decide(state, task_goal, history)
            finally:
                decide_total += time.perf_counter() - began
            meta = choice.get("_meta", {})
            input_tokens += int(meta.get("input_tokens", 0))
            output_tokens += int(meta.get("output_tokens", 0))
            cost += float(meta.get("cost_usd", cost_usd(int(meta.get("input_tokens", 0)))))
            selected_id = choice.get("choice")
            if selected_id == "none":
                raise _NoTarget("No suitable target was offered")
            action = next((item for item in state.get("actions", []) if item.get("id") == selected_id), None)
            if action:
                kind = action.get("kind", "")
                action_kind = "press-enter" if kind in {"press", "enter", "press_enter"} else kind
                reason = is_risky(action.get("label", ""), action.get("role"), action_kind)
                if reason and action_kind in {"click", "press-enter"}:
                    key = (action.get("label", ""), reason)
                    if not allow_risky_actions or key in approved_risky:
                        raise ApprovalRequired(choice, action.get("label", ""), reason)
                    approved_risky.add(key)
            return choice

        class TimedBrowser(_LockedBrowser):
            def _within_limits(self):
                if time.perf_counter() - started >= limits.timeout_s:
                    raise _RunLimit("Run timed out")
                if agent is not None and len(agent.state["history"]) >= limits.max_steps:
                    raise _RunLimit("Maximum steps reached")

            def observe(self, *args, **kwargs):
                self._within_limits()
                return super().observe(*args, **kwargs)

            def act(self, *args, **kwargs):
                self._within_limits()
                return super().act(*args, **kwargs)

        browser = TimedBrowser(raw_browser, NeoLock())
        agent = Agent(goal, browser=browser, decide=checked_decide)
        for _state in agent.run():
            if time.perf_counter() - started >= limits.timeout_s:
                raise _RunLimit("Run timed out")
        status = agent.state["status"]
    except ApprovalRequired as exc:
        status = "needs_approval"
        risky = {"label": exc.element_label, "reason": exc.reason}
        error = "User approval is required for this action"
    except _NoTarget as exc:
        status, error = "blocked", str(exc)
    except _RunLimit as exc:
        status, error = "limit", str(exc)
    except Exception as exc:
        logging.getLogger("clef_browse").error("task failed", exc_info=True, stack_info=False)
        status, error = "error", f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        if agent is not None:
            try:
                agent.close()
            except Exception:
                pass
        elif raw_browser is not None:
            try:
                raw_browser.close()
            except Exception:
                pass
        if tab is not None:
            try:
                close_tab(mcp, tab)
            except Exception as exc:
                if status == "done":
                    status, error = "error", f"{type(exc).__name__}: tab cleanup failed"
        if owned_mcp:
            try:
                mcp.close()
            except Exception:
                pass

    steps = len(agent.state["history"]) if agent is not None else 0
    page_data = agent.state.get("page") if agent is not None else None
    page = {"url": page_data.get("url", ""), "title": page_data.get("title", "")} if page_data else None
    tab_data = {"page_id": tab.page_id, "url": tab.url, "target_id": tab.target_id} if tab else None
    elapsed = time.perf_counter() - started
    browser_total = browser.browser_total if browser else 0.0
    timing = {
        "total": elapsed * 1000,
        "attach": attach_s * 1000,
        "decide_total": decide_total * 1000,
        "browser_total": browser_total * 1000,
        "decide_mean": (decide_total / model_calls * 1000) if model_calls else 0.0,
    }
    return _result(
        status,
        error=error,
        risky=risky,
        steps=steps,
        model_calls=model_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        timing=timing,
        tab=tab_data,
        page=page,
    )
