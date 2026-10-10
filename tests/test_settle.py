from __future__ import annotations

from clef_browse.settle import SETTLE_CAP_MS, wait_until_settled


class FakeBrowser:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def call(self, method, **params):
        self.calls.append((method, params))
        return self.response


def test_disabled_settle_does_not_touch_the_page():
    browser = FakeBrowser({})
    assert wait_until_settled(browser, 0) is None
    assert browser.calls == []


def test_settle_waits_in_the_page_with_a_quiet_window_and_a_cap():
    browser = FakeBrowser({"result": {"value": 640}})
    assert wait_until_settled(browser, 500) == 640
    method, params = browser.calls[0]
    assert method == "Runtime.evaluate"
    assert params["awaitPromise"] is True
    assert params["expression"].endswith(f")(500,{SETTLE_CAP_MS})")


def test_settle_gives_up_quietly_when_the_page_navigates():
    browser = FakeBrowser({"exceptionDetails": {"text": "Execution context was destroyed"}})
    assert wait_until_settled(browser, 500) is None
