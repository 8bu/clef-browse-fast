import json
import sys

from ._version import __version__
from .config import RunLimits, load_dotenv
from .executor import run_task

INSTRUCTIONS = (
    "Use browser_task for one small task on one page in the running BrowserOS Neo browser. "
    "Put the exact text to type in quotation marks, and write 'exactly'. "
    "Without the text, the model writes its own text. "
    "Never set allow_risky_actions to true until the user approves the exact action. "
    "The result has a status and the final URL. It does not have page text."
)

TOOL = {
    "name": "browser_task",
    "description": (
        "Run one task in plain English on one page in the running BrowserOS Neo browser. "
        "The tool opens its own tab and closes it at the end. "
        "It stops with status needs_approval before a risky click, such as delete, send, pay, or Post. "
        "It returns a status, the final URL, and the title. It does not return page text."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The page to open first. Use a full http or https URL."},
            "goal": {
                "type": "string",
                "description": (
                    "One task. Name each control with the label that the page shows. "
                    "Put the exact text to type in quotation marks, and write 'exactly'. "
                    "End with a finish condition that the page shows, "
                    "for example: You are done when the heading says 'Welcome'."
                ),
            },
            "allow_risky_actions": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Default false. Set true only after the user approves the exact risky action. "
                    "A label check finds the risky controls. A risky control with a neutral label passes."
                ),
            },
            "max_steps": {"type": "integer", "description": "Maximum number of actions. Lower it for small tasks."},
            "timeout_s": {"type": "number", "description": "Maximum run time in seconds."},
        },
        "required": ["url", "goal"],
        "additionalProperties": False,
    },
}


def handle_request(request: dict) -> dict | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "clef-browse-fast", "version": __version__},
                "instructions": INSTRUCTIONS,
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": [TOOL]}}
    if method == "tools/call":
        params = request.get("params", {})
        if params.get("name") != "browser_task":
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Unknown tool"}}
        args = params.get("arguments", {})
        limits = RunLimits.from_env()
        result = run_task(
            args["url"],
            args["goal"],
            allow_risky_actions=args.get("allow_risky_actions", False),
            limits=RunLimits(
                max_steps=args.get("max_steps", limits.max_steps),
                timeout_s=args.get("timeout_s", limits.timeout_s),
                max_model_calls=limits.max_model_calls,
                settle_ms=limits.settle_ms,
            ),
        )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, separators=(",", ":"))}],
                "isError": result["status"] == "error",
            },
        }
    if request_id is not None:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
    return None


def handle_line(line: str) -> str | None:
    response = handle_request(json.loads(line))
    return json.dumps(response, separators=(",", ":")) if response is not None else None


def main() -> int:
    load_dotenv()
    for line in sys.stdin:
        try:
            response = handle_line(line)
        except Exception:
            print("MCP request failed", file=sys.stderr)
            response = json.dumps(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": "Internal error"}}
            )
        if response is not None:
            sys.stdout.write(response + "\n")
            sys.stdout.flush()
    return 0
