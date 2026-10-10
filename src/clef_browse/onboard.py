"""Guided first-run setup.

Every step explains what it does. A change to a file needs a yes from the user.
The module never prints a token.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .config import user_config_path
from .executor import run_task
from .health import neo_status

CLOUDFLARE_TOKEN_URL = "https://dash.cloudflare.com/profile/api-tokens"
DEFAULT_TEXT_URL = "https://api.deepseek.com/v1"
DEFAULT_TEXT_MODEL = "deepseek-chat"
TEST_URL = "https://example.com"
TEST_GOAL = "Click the 'Learn more' link. You are done when the page heading says 'Example Domains'."
MCP_NAME = "clef-browse"
SKILL_NAME = "clef-browse-fast"
STEPS = 6


@dataclass
class Console:
    """The input and output of the guide. Tests replace these functions."""

    say: Callable[[str], None] = print
    ask: Callable[[str], str] = input
    secret: Callable[[str], str] = getpass.getpass

    def confirm(self, question: str, default: bool = True) -> bool:
        hint = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self.ask(f"{question} {hint} ").strip().lower()
            if not answer:
                return default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False
            self.say("Type y or n.")


@dataclass(frozen=True)
class Paths:
    settings: Path
    omp_dir: Path

    @classmethod
    def default(cls) -> Paths:
        return cls(settings=user_config_path(), omp_dir=Path.home() / ".omp" / "agent")

    @property
    def mcp_json(self) -> Path:
        return self.omp_dir / "mcp.json"

    @property
    def skill_file(self) -> Path:
        return self.omp_dir / "skills" / SKILL_NAME / "SKILL.md"


def mcp_command() -> str | None:
    """The full path of the MCP server program in the environment that runs this code."""
    sibling = Path(sys.executable).parent / "clef-browse-mcp"
    if sibling.is_file():
        return str(sibling)
    return shutil.which("clef-browse-mcp")


@dataclass
class Hooks:
    """The parts of the outside world that setup uses. Tests replace them."""

    neo_status: Callable[[], dict[str, bool]] = neo_status
    run_task: Callable[..., dict] = run_task
    mcp_command: Callable[[], str | None] = mcp_command


def _atomic_write(path: Path, text: str, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_settings(path: Path, updates: dict[str, str]) -> None:
    """Set the given keys in a settings file. Keep every other line. Make the file private."""
    for key, value in updates.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or "\n" in value or "\r" in value:
            raise ValueError(f"Invalid setting: {key}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = path.resolve()
    lines = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    pending = dict(updates)
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in pending:
            lines[index] = f"{key}={pending.pop(key)}"
    lines += [f"{key}={value}" for key, value in pending.items()]
    _atomic_write(target, "\n".join(lines) + "\n", 0o600)


def _heading(console: Console, number: int, title: str) -> None:
    console.say("")
    console.say(f"Step {number} of {STEPS}: {title}")


def _step_neo(console: Console, hooks: Hooks) -> None:
    _heading(console, 1, "BrowserOS Neo")
    console.say("This tool controls the BrowserOS Neo app that runs on your computer. Neo must be open.")
    while True:
        status = hooks.neo_status()
        if all(status.values()):
            console.say("Neo answers on both ports.")
            return
        console.say("Neo does not answer. Open the BrowserOS Neo app.")
        if not console.confirm("Try again?"):
            console.say("Skipped. Run `clef-browse check` after you open Neo.")
            return


def _step_cloudflare(console: Console, updates: dict[str, str]) -> bool:
    _heading(console, 2, "Cloudflare (the decision model)")
    console.say("A model named Clef picks each click. It runs on Cloudflare Workers AI. A task costs under one cent.")
    console.say("Clef reads the text of the page. Cloudflare receives that text. See docs/safety.md.")
    if os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_AUTH_TOKEN"):
        console.say("Cloudflare settings already exist.")
        if console.confirm("Keep them?"):
            return True
    console.say(f"Create a token at {CLOUDFLARE_TOKEN_URL}")
    console.say("Give it the Workers AI Read and Edit permissions for one account. Set an expiry date.")
    while True:
        account = console.ask("Cloudflare account ID (32 letters and digits, empty to stop): ").strip()
        if not account:
            console.say("Setup stopped. The Cloudflare account ID is required.")
            return False
        if re.fullmatch(r"[0-9a-fA-F]{32}", account):
            break
        console.say("That is not an account ID. An account ID has 32 letters and digits.")
    token = console.secret("Cloudflare API token (the screen shows nothing while you type): ").strip()
    if not token:
        console.say("Setup stopped. The token is required.")
        return False
    updates["CLOUDFLARE_ACCOUNT_ID"] = account
    updates["CLOUDFLARE_AUTH_TOKEN"] = token
    return True


def _step_text_provider(console: Console, updates: dict[str, str]) -> None:
    _heading(console, 3, "Text provider (optional)")
    console.say("Clef chooses the field. A second model writes the text that goes into a field.")
    console.say("You need it only when a task types text. That model sees your goal and the field label.")
    if os.environ.get("TEXT_MODEL_API_KEY"):
        console.say("A text provider already exists.")
        if console.confirm("Keep it?"):
            return
    elif not console.confirm("Add a text provider now?", default=False):
        console.say("Skipped. Run `clef-browse setup` again to add it.")
        return
    console.say("Use any OpenAI-compatible service.")
    updates["TEXT_MODEL_BASE_URL"] = console.ask(f"Base URL [{DEFAULT_TEXT_URL}]: ").strip() or DEFAULT_TEXT_URL
    updates["TEXT_MODEL"] = console.ask(f"Model [{DEFAULT_TEXT_MODEL}]: ").strip() or DEFAULT_TEXT_MODEL
    key = console.secret("API key (the screen shows nothing while you type): ").strip()
    if key:
        updates["TEXT_MODEL_API_KEY"] = key
    else:
        console.say("No key entered. The text settings are saved without a key.")


def _step_save(console: Console, paths: Paths, updates: dict[str, str]) -> bool:
    _heading(console, 4, "Save your settings")
    if not updates:
        console.say("Nothing new to save.")
        return True
    console.say(f"File: {paths.settings}")
    console.say(f"Keys to write: {', '.join(updates)}")
    console.say("Only you can read the file. The tool never prints your token.")
    if not console.confirm("Save these settings?"):
        console.say("Nothing was saved.")
        return False
    write_settings(paths.settings, updates)
    os.environ.update(updates)
    console.say("Saved.")
    if Path(".env").is_file():
        console.say("Note: a `.env` file in this folder overrides the saved settings here.")
    return True


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _step_register(console: Console, paths: Paths, command: str | None) -> None:
    _heading(console, 5, "Connect to OMP and install the skill")
    if command is None:
        console.say("Could not find the program `clef-browse-mcp`. Install the package with `uv tool install`.")
    else:
        entry = {"type": "stdio", "command": command, "args": [], "timeout": 300000}
        console.say(f"MCP server: {command}")
        console.say("For another MCP client, add a stdio server with this command and no arguments.")
        _register_mcp(console, paths.mcp_json, entry)
    _install_skill(console, paths.omp_dir, paths.skill_file)


def _register_mcp(console: Console, path: Path, entry: dict) -> None:
    if not path.is_file():
        console.say(f"OMP config not found at {path}. Skipped.")
        return
    target = path.resolve()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        console.say(f"{path} is not valid JSON. Skipped. The file is unchanged.")
        return
    servers = data.setdefault("mcpServers", {})
    current = servers.get(MCP_NAME)
    if current == entry:
        console.say("The MCP server is already registered in OMP.")
        return
    question = f"Update the `{MCP_NAME}` entry in {path}?" if current else f"Add the MCP server to {path}?"
    if not console.confirm(question, default=current is None):
        console.say("Skipped. The file is unchanged.")
        return
    backup = target.with_name(f"{target.name}.bak-{_timestamp()}")
    shutil.copy2(target, backup)
    servers[MCP_NAME] = entry
    _atomic_write(target, json.dumps(data, indent=2) + "\n", target.stat().st_mode & 0o777)
    console.say(f"Added. Backup: {backup}")


def _install_skill(console: Console, omp_dir: Path, path: Path) -> None:
    if not omp_dir.is_dir():
        console.say(f"OMP folder not found at {omp_dir}. Skill skipped.")
        return
    text = files("clef_browse").joinpath("skill/SKILL.md").read_text(encoding="utf-8")
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        console.say("The skill is already installed.")
        return
    question = (
        f"The skill at {path} is different. Replace it?" if path.is_file() else f"Install the skill to {path}?"
    )
    if not console.confirm(question, default=not path.is_file()):
        console.say("Skipped.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path.resolve() if path.exists() else path, text, 0o644)
    console.say("Installed. Start a new OMP session to load it.")


def _step_test(console: Console, hooks: Hooks) -> bool:
    _heading(console, 6, "Test")
    console.say(f"The test opens a tab on {TEST_URL} in Neo for a few seconds and closes it.")
    if not console.confirm("Run the test now?"):
        console.say("Skipped. Run `clef-browse check` at any time.")
        return True
    result = hooks.run_task(TEST_URL, TEST_GOAL)
    console.say(f"Status: {result['status']}")
    if result["status"] == "done":
        console.say("The tool works.")
        return True
    error = str(result.get("error") or "")
    console.say(f"Error: {error or 'none'}")
    if "HTTP 401" in error or "HTTP 403" in error:
        console.say("Cloudflare rejected the token. Check the account ID and the Workers AI Read and Edit permissions.")
    else:
        console.say("See docs/troubleshooting.md.")
    return False


def run_setup(console: Console | None = None, paths: Paths | None = None, hooks: Hooks | None = None) -> int:
    console = console or Console()
    paths = paths or Paths.default()
    hooks = hooks or Hooks()
    updates: dict[str, str] = {}
    try:
        console.say("clef-browse setup. It takes about two minutes.")
        console.say("It asks before it changes a file. Press Ctrl+C at any time to stop.")
        _step_neo(console, hooks)
        if not _step_cloudflare(console, updates):
            return 1
        _step_text_provider(console, updates)
        if not _step_save(console, paths, updates):
            return 1
        _step_register(console, paths, hooks.mcp_command())
        ok = _step_test(console, hooks)
    except (KeyboardInterrupt, EOFError):
        console.say("")
        console.say("Setup stopped. Files that you already saved stay as they are.")
        return 130
    console.say("")
    done = "Setup is complete."
    failed = "Settings are saved. The test failed. Fix the cause and run setup again."
    console.say(done if ok else failed)
    return 0 if ok else 1
