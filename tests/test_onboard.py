import json
import os
import stat
from importlib.resources import files

import pytest

from clef_browse import cli
from clef_browse.config import load_settings
from clef_browse.onboard import Console, Hooks, Paths, run_setup, write_settings

ACCOUNT = "0123456789abcdef0123456789abcdef"
TOKEN = "cf-secret-token-value"
TEXT_KEY = "text-secret-key-value"
SERVER = "/opt/tool/bin/clef-browse-mcp"
SETTING_KEYS = (
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_AUTH_TOKEN",
    "TEXT_MODEL_API_KEY",
    "TEXT_MODEL",
    "CLEF_BROWSE_CONFIG",
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A private environment: no real settings, an empty working folder, and a fake OMP folder."""
    monkeypatch.setattr(os, "environ", {k: v for k, v in os.environ.items() if k not in SETTING_KEYS})
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    omp = tmp_path / "omp"
    omp.mkdir()
    return tmp_path


class Script:
    def __init__(self, answers, secrets=()):
        self.answers = list(answers)
        self.secrets = list(secrets)
        self.said: list[str] = []

    def _ask(self, prompt):
        assert self.answers, f"unexpected prompt: {prompt}"
        return self.answers.pop(0)

    def _secret(self, prompt):
        assert self.secrets, f"unexpected secret prompt: {prompt}"
        return self.secrets.pop(0)

    @property
    def console(self):
        return Console(say=self.said.append, ask=self._ask, secret=self._secret)

    @property
    def output(self):
        return "\n".join(self.said)


def make_hooks(result=None, neo=None):
    calls = []

    def fake_run(url, goal):
        calls.append((url, goal))
        return result or {"status": "done", "error": None}

    hooks = Hooks(
        neo_status=lambda: neo or {"neo_mcp": True, "neo_cdp": True},
        run_task=fake_run,
        mcp_command=lambda: SERVER,
    )
    return hooks, calls


def make_paths(home):
    return Paths(settings=home / "config" / "clef-browse" / ".env", omp_dir=home / "omp")


def write_mcp(home, servers):
    path = home / "omp" / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n")
    return path


HAPPY_ANSWERS = [ACCOUNT, "y", "", "", "y", "y", "y", "y"]
HAPPY_SECRETS = [TOKEN, TEXT_KEY]


def test_settings_load_from_environment_then_local_file_then_user_file(home, monkeypatch):
    user_file = home / "user.env"
    user_file.write_text("CLOUDFLARE_ACCOUNT_ID=from-user\nCLOUDFLARE_AUTH_TOKEN=from-user\nTEXT_MODEL=from-user\n")
    (home / "work" / ".env").write_text("CLOUDFLARE_AUTH_TOKEN=from-local\nTEXT_MODEL=from-local\n")
    os.environ["CLEF_BROWSE_CONFIG"] = str(user_file)
    os.environ["TEXT_MODEL"] = "from-env"
    load_settings()
    assert os.environ["CLOUDFLARE_ACCOUNT_ID"] == "from-user"
    assert os.environ["CLOUDFLARE_AUTH_TOKEN"] == "from-local"
    assert os.environ["TEXT_MODEL"] == "from-env"


def test_write_settings_keeps_other_lines_and_makes_the_file_private(home):
    path = home / "config" / "clef-browse" / ".env"
    path.parent.mkdir(parents=True)
    path.write_text("# my notes\nKEEP=1\nTEXT_MODEL=old\n")
    write_settings(path, {"TEXT_MODEL": "new", "CLOUDFLARE_ACCOUNT_ID": ACCOUNT})
    assert path.read_text() == f"# my notes\nKEEP=1\nTEXT_MODEL=new\nCLOUDFLARE_ACCOUNT_ID={ACCOUNT}\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_settings_creates_a_private_folder(home):
    path = home / "fresh" / "clef-browse" / ".env"
    write_settings(path, {"TEXT_MODEL": "x"})
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_write_settings_rejects_a_value_that_would_add_a_line(home):
    with pytest.raises(ValueError):
        write_settings(home / ".env", {"TEXT_MODEL": "x\nCLOUDFLARE_AUTH_TOKEN=stolen"})


def test_guided_setup_saves_registers_installs_and_tests(home):
    paths = make_paths(home)
    mcp = write_mcp(home, {"other": {"type": "stdio", "command": "other"}})
    original = mcp.read_text()
    script = Script(HAPPY_ANSWERS, HAPPY_SECRETS)
    hooks, calls = make_hooks()

    assert run_setup(script.console, paths, hooks) == 0

    saved = paths.settings.read_text()
    assert f"CLOUDFLARE_ACCOUNT_ID={ACCOUNT}" in saved
    assert f"CLOUDFLARE_AUTH_TOKEN={TOKEN}" in saved
    assert "TEXT_MODEL_BASE_URL=https://api.deepseek.com/v1" in saved
    assert stat.S_IMODE(paths.settings.stat().st_mode) == 0o600
    servers = json.loads(mcp.read_text())["mcpServers"]
    assert servers["other"] == {"type": "stdio", "command": "other"}
    assert servers["clef-browse"]["command"] == SERVER
    [backup] = list((home / "omp").glob("mcp.json.bak-*"))
    assert backup.read_text() == original
    skill = home / "omp" / "skills" / "clef-browse-fast" / "SKILL.md"
    assert skill.read_text() == files("clef_browse").joinpath("skill/SKILL.md").read_text()
    assert [url for url, _ in calls] == ["https://example.com"]
    assert TOKEN not in script.output and TEXT_KEY not in script.output


def test_declining_the_save_changes_nothing(home):
    paths = make_paths(home)
    mcp = write_mcp(home, {})
    before = mcp.read_text()
    script = Script([ACCOUNT, "n", "n"], [TOKEN])
    hooks, calls = make_hooks()

    assert run_setup(script.console, paths, hooks) == 1

    assert not paths.settings.exists()
    assert mcp.read_text() == before
    assert not (home / "omp" / "skills").exists()
    assert calls == []


def test_existing_cloudflare_settings_are_kept_without_asking_for_the_token(home):
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT
    os.environ["CLOUDFLARE_AUTH_TOKEN"] = TOKEN
    paths = make_paths(home)
    script = Script(["y", "n", "n", "n", "n"], [])
    hooks, _ = make_hooks()

    assert run_setup(script.console, paths, hooks) == 0
    assert not paths.settings.exists()


def test_a_wrong_account_id_is_asked_again(home):
    script = Script(["not-an-id", ACCOUNT, "n", "y", "n", "n", "n"], [TOKEN])
    hooks, _ = make_hooks()
    paths = make_paths(home)

    assert run_setup(script.console, paths, hooks) == 0
    assert f"CLOUDFLARE_ACCOUNT_ID={ACCOUNT}" in paths.settings.read_text()
    assert "not an account ID" in script.output


def test_a_mcp_file_that_is_not_json_is_never_overwritten(home):
    bad = home / "omp" / "mcp.json"
    bad.write_text("{ not json")
    script = Script([ACCOUNT, "n", "y", "n", "n"], [TOKEN])
    hooks, _ = make_hooks()

    assert run_setup(script.console, make_paths(home), hooks) == 0
    assert bad.read_text() == "{ not json"
    assert list((home / "omp").glob("mcp.json.bak-*")) == []


def test_a_different_existing_entry_is_kept_unless_the_user_says_yes(home):
    mcp = write_mcp(home, {"clef-browse": {"type": "stdio", "command": "/old/path"}})
    script = Script([ACCOUNT, "n", "y", "", "n", "n"], [TOKEN])
    hooks, _ = make_hooks()

    assert run_setup(script.console, make_paths(home), hooks) == 0
    assert json.loads(mcp.read_text())["mcpServers"]["clef-browse"]["command"] == "/old/path"


def test_an_entry_that_is_already_correct_is_not_rewritten(home):
    entry = {"type": "stdio", "command": SERVER, "args": [], "timeout": 300000}
    write_mcp(home, {"clef-browse": entry})
    script = Script([ACCOUNT, "n", "y", "y", "n"], [TOKEN])
    hooks, _ = make_hooks()

    assert run_setup(script.console, make_paths(home), hooks) == 0
    assert list((home / "omp").glob("mcp.json.bak-*")) == []
    assert "already registered" in script.output


def test_a_rejected_token_is_explained_and_the_settings_stay_saved(home):
    script = Script([ACCOUNT, "n", "y", "n", "y"], [TOKEN])
    hooks, _ = make_hooks(result={"status": "error", "error": "Clef returned HTTP 401"})
    paths = make_paths(home)

    assert run_setup(script.console, paths, hooks) == 1
    assert "Workers AI Read and Edit" in script.output
    assert f"CLOUDFLARE_AUTH_TOKEN={TOKEN}" in paths.settings.read_text()
    assert TOKEN not in script.output


def test_setup_waits_for_neo_and_continues_when_it_opens(home):
    states = iter([{"neo_mcp": False, "neo_cdp": False}, {"neo_mcp": True, "neo_cdp": True}])
    hooks, _ = make_hooks()
    hooks.neo_status = lambda: next(states)
    script = Script(["y", ACCOUNT, "n", "y", "n", "n"], [TOKEN])

    assert run_setup(script.console, make_paths(home), hooks) == 0
    assert "Neo does not answer" in script.output
    assert "Neo answers on both ports" in script.output


def test_setup_can_skip_the_neo_check(home):
    hooks, _ = make_hooks(neo={"neo_mcp": False, "neo_cdp": False})
    script = Script(["n", ACCOUNT, "n", "y", "n", "n"], [TOKEN])

    assert run_setup(script.console, make_paths(home), hooks) == 0
    assert "clef-browse check" in script.output


def test_ctrl_c_stops_without_a_traceback(home):
    def interrupt(prompt):
        raise KeyboardInterrupt

    console = Console(say=lambda text: None, ask=interrupt, secret=interrupt)
    hooks, _ = make_hooks(neo={"neo_mcp": False, "neo_cdp": False})

    assert run_setup(console, make_paths(home), hooks) == 130


def test_setup_command_needs_a_terminal(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda: None)
    assert cli.main(["setup"]) == 2
    assert "needs a terminal" in capsys.readouterr().err
