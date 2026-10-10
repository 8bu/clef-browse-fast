from __future__ import annotations

import json
from urllib.request import urlopen

import pytest
from fake_neo import FakeNeo

from clef_browse.config import RunLimits
from clef_browse.executor import run_task
from clef_browse.neo import NeoMcp


@pytest.fixture
def neo_server(test_cdp_url):
    with FakeNeo(test_cdp_url) as server:
        yield server


def _decision_for(action: dict | None) -> dict:
    if action is None:
        return {
            "choice": "DONE",
            "operation": "DONE",
            "target": None,
            "confidence": 1.0,
            "probabilities": {"DONE": 1.0},
            "operation_probabilities": {"DONE": 1.0},
            "target_probabilities": {},
            "target_confidence": None,
            "raw_answers": {},
            "latency_ms": 0.0,
            "usage": {},
            "_meta": {},
        }
    operation = {"click": "CLICK", "fill": "TYPE_TEXT", "select": "SELECT"}[action["kind"]]
    return {
        "choice": action["id"],
        "operation": operation,
        "target": str(action["node"]),
        "confidence": 1.0,
        "probabilities": {action["id"]: 1.0},
        "operation_probabilities": {operation: 1.0},
        "target_probabilities": {str(action["node"]): 1.0},
        "target_confidence": 1.0,
        "raw_answers": {},
        "latency_ms": 0.0,
        "usage": {},
        "_meta": {"input_tokens": 0, "output_tokens": 0},
    }


def _run(monkeypatch, neo_server, test_cdp_url, site_url, selectors, *, allow_risky_actions=False):
    monkeypatch.setenv("BROWSEROS_NEO_CDP_URL", test_cdp_url)
    monkeypatch.setenv("BROWSEROS_NEO_MCP_URL", neo_server.url)
    from jev_ultrafast import agent as agent_module

    monkeypatch.setattr(
        agent_module,
        "field_text",
        lambda *_args, **_kwargs: ("Mina", {"model": "mock", "latency_ms": 0}),
    )
    remaining = list(selectors)

    def decide(page, _goal, _history):
        selected = remaining.pop(0)
        if selected == "DONE":
            return _decision_for(None)
        action = next(
            item
            for item in page["actions"]
            if item["kind"] == selected[0]
            and selected[1].casefold() in item["label"].casefold()
            and (selected[2] is None or item.get("value") == selected[2])
        )
        return _decision_for(action)

    client = NeoMcp(neo_server.url)
    try:
        result = run_task(
            site_url,
            "Complete the local test form",
            allow_risky_actions=allow_risky_actions,
            decide=decide,
            mcp=client,
        )
    finally:
        client.close()
    assert not remaining
    return result


def _closed_state(neo_server, result):
    assert result["tab"] is not None
    return neo_server.closed_pages[result["tab"]["page_id"]]


def test_click_save_updates_status(monkeypatch, neo_server, test_cdp_url, site_url):
    result = _run(monkeypatch, neo_server, test_cdp_url, site_url, [("click", "Save", None), "DONE"])
    assert result["status"] == "done"
    assert _closed_state(neo_server, result)["status"] == "saved:Ada:medium"


def test_fill_name_and_select_size_then_save(monkeypatch, neo_server, test_cdp_url, site_url):
    result = _run(
        monkeypatch,
        neo_server,
        test_cdp_url,
        site_url,
        [("fill", "Name", None), ("select", "Large", "large"), ("click", "Save", None), "DONE"],
    )
    assert result["status"] == "done"
    assert _closed_state(neo_server, result)["status"] == "saved:Mina:large"


def test_submit_requires_approval_and_preserves_status(monkeypatch, neo_server, test_cdp_url, site_url):
    result = _run(monkeypatch, neo_server, test_cdp_url, site_url, [("click", "Submit order", None)])
    assert result["status"] == "needs_approval"
    assert _closed_state(neo_server, result)["status"] == ""


def test_approved_submit_updates_status(monkeypatch, neo_server, test_cdp_url, site_url):
    result = _run(
        monkeypatch,
        neo_server,
        test_cdp_url,
        site_url,
        [("click", "Submit order", None), "DONE"],
        allow_risky_actions=True,
    )
    assert result["status"] == "done"
    assert _closed_state(neo_server, result)["status"] == "submitted"


def test_run_does_not_touch_tabs_not_created_by_fake(neo_server, test_cdp_url, site_url, monkeypatch):
    with urlopen(f"{test_cdp_url}/json/list", timeout=5) as response:
        before = {target["id"] for target in json.load(response)}
    result = _run(monkeypatch, neo_server, test_cdp_url, site_url, [("click", "Save", None), "DONE"])
    with urlopen(f"{test_cdp_url}/json/list", timeout=5) as response:
        after = {target["id"] for target in json.load(response)}
    assert result["status"] == "done"
    assert after == before


def _first_observation_labels(monkeypatch, neo_server, test_cdp_url, url, settle_ms):
    monkeypatch.setenv("BROWSEROS_NEO_CDP_URL", test_cdp_url)
    monkeypatch.setenv("BROWSEROS_NEO_MCP_URL", neo_server.url)
    seen = []

    def decide(page, _goal, _history):
        seen.append([item["label"] for item in page["actions"]])
        return _decision_for(None)

    client = NeoMcp(neo_server.url)
    try:
        result = run_task(url, "look", decide=decide, mcp=client, limits=RunLimits(settle_ms=settle_ms))
    finally:
        client.close()
    assert result["status"] == "done"
    return seen[0]


def test_first_observation_waits_for_a_button_that_enables_late(monkeypatch, neo_server, test_cdp_url, site_url):
    labels = _first_observation_labels(monkeypatch, neo_server, test_cdp_url, site_url + "slow.html", 500)
    assert "Later" in labels


def test_without_settle_the_late_button_is_missed(monkeypatch, neo_server, test_cdp_url, site_url):
    labels = _first_observation_labels(monkeypatch, neo_server, test_cdp_url, site_url + "slow.html", 0)
    assert "Later" not in labels
