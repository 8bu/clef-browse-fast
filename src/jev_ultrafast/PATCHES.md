# Local changes to jev-ultrafast

Upstream: https://github.com/browser-use/jev-ultrafast, commit `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`.
The file `UPSTREAM_SHA` holds the same commit. The upstream license is in `LICENSE.upstream`.

Keep this list short. Put new code in `clef_browse/` and not in this folder.

1. The upstream `static/` folder (the web UI) and `demo.py` are removed. They use the upstream hosted decision endpoint.
2. `model.py`: the upstream hosted `choose()` function and its endpoint are removed. The function
   `clef_browse.clef.choose` replaces it. The functions `action_space`, `field_text`, and `field_context` are unchanged.
3. `agent.py`: `Agent` receives the `browser` and `decide` callables as arguments. It no longer builds them.
   `StalePage` comes from `errors.py`.
4. `browser.py`: `Browser(url, *, target_id, cdp)` attaches to an existing target through a `cdp` callable. The signature
   of the callable is `cdp(method, session_id=None, **params)`.
   - The `browser_harness` imports are removed.
   - The calls to `Target.createTarget` and `Target.closeTarget` are removed.
   - `close()` only detaches the session.
   - `browser_operation` takes the `cdp` callable as its first argument.
5. `errors.py` is new. It holds `StalePage`, so that `agent.py` does not import `browser.py`.
