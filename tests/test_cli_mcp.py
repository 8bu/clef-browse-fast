import json

from clef_browse import cli, mcp_server


def test_mcp_tells_the_caller_how_to_use_each_field():
    init = json.loads(mcp_server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})))
    assert init["result"]["capabilities"] == {"tools": {}}
    assert init["result"]["instructions"]
    listed = json.loads(mcp_server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})))
    properties = listed["result"]["tools"][0]["inputSchema"]["properties"]
    assert [name for name, spec in properties.items() if not spec.get("description")] == []


def test_mcp_initialize_tools_list_and_call(monkeypatch):
    monkeypatch.setattr(mcp_server, "run_task", lambda *args, **kwargs: {"status": "done"})
    init = json.loads(mcp_server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})))
    assert init["result"]["protocolVersion"] == "2025-06-18"
    listed = json.loads(mcp_server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})))
    assert listed["result"]["tools"][0]["name"] == "browser_task"
    assert listed["result"]["tools"][0]["inputSchema"]["required"] == ["url", "goal"]
    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "browser_task", "arguments": {"url": "https://example.test", "goal": "go"}},
    }
    called = json.loads(mcp_server.handle_line(json.dumps(request)))
    assert json.loads(called["result"]["content"][0]["text"]) == {"status": "done"}
    assert called["result"]["isError"] is False
    assert mcp_server.handle_line(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})) is None


def test_cli_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda: None)
    monkeypatch.setattr(
        cli, "run_task", lambda *args, **kwargs: {"status": "done", "outcome": "done", "risky": None, "error": None}
    )
    assert cli.main(["run", "--url", "https://example.test", "--goal", "go", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "done"
    monkeypatch.setattr(
        cli,
        "run_task",
        lambda *args, **kwargs: {
            "status": "needs_approval",
            "outcome": None,
            "risky": {"reason": "submit", "label": "Submit"},
            "error": None,
        },
    )
    assert cli.main(["run", "--url", "https://example.test", "--goal", "go"]) == 2
    monkeypatch.setattr(
        cli, "run_task", lambda *args, **kwargs: {"status": "error", "outcome": None, "risky": None, "error": "failed"}
    )
    assert cli.main(["run", "--url", "https://example.test", "--goal", "go"]) == 1
