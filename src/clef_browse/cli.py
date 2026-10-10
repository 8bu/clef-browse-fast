import argparse
import json
import os
import sys

import httpx

from .config import RunLimits, load_dotenv, neo_urls
from .executor import run_task


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clef-browse")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--url", required=True)
    run.add_argument("--goal", required=True)
    run.add_argument("--allow-risky-actions", action="store_true")
    run.add_argument("--max-steps", type=int)
    run.add_argument("--timeout-s", type=float)
    run.add_argument("--json", action="store_true")
    commands.add_parser("check")
    return parser


def _check() -> dict[str, bool]:
    mcp_url, cdp_url = neo_urls()
    mcp_ok = cdp_ok = False
    try:
        from .neo import NeoMcp

        client = NeoMcp(mcp_url)
        client.call_tool("run", {"code": "return (await browser.pages.list()).length"})
        client.close()
        mcp_ok = True
    except Exception:
        pass
    try:
        response = httpx.get(f"{cdp_url.rstrip('/')}/json/version", timeout=3)
        cdp_ok = response.is_success and str(response.json().get("Browser", "")).startswith("Chrome/")
    except Exception:
        pass
    return {
        "neo_mcp": mcp_ok,
        "neo_cdp": cdp_ok,
        "clef_env": bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_AUTH_TOKEN")),
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _parser().parse_args(argv)
    if args.command == "check":
        checks = _check()
        print(json.dumps(checks, sort_keys=True))
        return 0 if all(checks.values()) else 1
    defaults = RunLimits.from_env()
    limits = RunLimits(
        max_steps=args.max_steps if args.max_steps is not None else defaults.max_steps,
        timeout_s=args.timeout_s if args.timeout_s is not None else defaults.timeout_s,
        max_model_calls=defaults.max_model_calls,
        settle_ms=defaults.settle_ms,
    )
    result = run_task(args.url, args.goal, allow_risky_actions=args.allow_risky_actions, limits=limits)
    if args.json:
        print(json.dumps(result, separators=(",", ":")))
    else:
        print(f"Status: {result['status']}")
        if result["outcome"]:
            print(f"Outcome: {result['outcome']}")
        if result["risky"]:
            print(f"Approval required: {result['risky']['reason']} — {result['risky']['label']}")
        if result["error"]:
            print(f"Error: {result['error']}", file=sys.stderr)
    return 0 if result["status"] == "done" else 2 if result["status"] == "needs_approval" else 1
