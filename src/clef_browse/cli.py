import argparse
import json
import sys

from .config import RunLimits, load_settings
from .executor import run_task
from .health import check_all
from .onboard import run_setup


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
    commands.add_parser("check", help="Check that Neo and the Cloudflare settings are ready.")
    commands.add_parser("setup", help="Guided first-run setup. Asks before it changes a file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_settings()
    args = _parser().parse_args(argv)
    if args.command == "setup":
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("setup needs a terminal. Run it in your own shell.", file=sys.stderr)
            return 2
        return run_setup()
    if args.command == "check":
        checks = check_all()
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
