"""Wait until a page stops changing, so the first observation sees a loaded page.

`readyState == "complete"` is too early for apps that hydrate after load. In a measured case a button was
disabled for about 1 s after load, the engine skipped it, and the task ended `blocked`.
"""

from __future__ import annotations

SETTLE_CAP_MS = 3000

# Resolves after `quietMs` without any DOM change, or after `capMs`, whichever comes first.
_SETTLE_JS = """((quietMs, capMs) => new Promise(resolve => {
  const started = performance.now();
  let timer;
  const finish = () => {
    observer.disconnect();
    clearTimeout(timer);
    resolve(Math.round(performance.now() - started));
  };
  const arm = () => { clearTimeout(timer); timer = setTimeout(finish, quietMs); };
  const observer = new MutationObserver(arm);
  observer.observe(document.documentElement, {subtree: true, childList: true, attributes: true, characterData: true});
  arm();
  setTimeout(finish, capMs);
}))"""


def wait_until_settled(browser, quiet_ms: int, cap_ms: int = SETTLE_CAP_MS) -> int | None:
    """Return the milliseconds waited, or None when disabled or when the page navigated meanwhile."""
    if quiet_ms <= 0:
        return None
    response = browser.call(
        "Runtime.evaluate",
        expression=f"({_SETTLE_JS})({int(quiet_ms)},{int(cap_ms)})",
        awaitPromise=True,
        returnByValue=True,
    )
    if response.get("exceptionDetails"):
        return None  # The document changed under the wait; the first observation handles that.
    return response.get("result", {}).get("value")
