# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.1.0 (not released)

### Added

- The command `clef-browse run` runs a browser task in a running BrowserOS Neo browser.
- The command `clef-browse check` tests the setup and prints no secrets.
- The MCP server `clef-browse-mcp` with the tool `browser_task`.
- A decision client for Cloudflare Clef. It accepts only the model `clef`.
- A small CDP client that attaches to one Neo tab.
- An approval gate for risky clicks and Enter key presses.
- Limits for steps, time, and Clef requests.
- A cost value in each result, based on the input tokens of the task.
- A wait for the page to stop changing before the first observation. The setting is `CLEF_BROWSE_SETTLE_MS`.
- Usage rules in the MCP tool description, in the field descriptions, and in the server instructions.
- An agent skill in `skills/clef-browse-fast/SKILL.md`.
- A copy of `browser-use/jev-ultrafast` at commit `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`, with local changes.
- Tests with a mocked Clef, a fake Neo MCP server, and a local test page.
- Documents in the `docs/` folder.
