from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _unavailable(reason: str) -> None:
    """Skip on a developer machine. Fail in CI, where a skip would hide a broken test run."""
    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(reason)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def site_url():
    port = _free_port()
    process = subprocess.Popen(
        ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT / "site")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail("Local test page server exited before becoming ready")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.02)
    else:
        process.terminate()
        pytest.fail("Local test page server did not become ready")
    yield url
    process.terminate()
    process.wait(timeout=5)


def _chrome_binary() -> str | None:
    mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac_chrome.is_file():
        return str(mac_chrome)
    return shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium")


def _stop(process: subprocess.Popen) -> None:
    """Stop Chrome and its child processes. A wrapper script can hide the real browser."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


@pytest.fixture(scope="session")
def test_cdp_url():
    binary = _chrome_binary()
    if not binary:
        _unavailable("Chrome is required for browser integration tests; install Google Chrome or Chromium")
    port = _free_port()
    profile = tempfile.TemporaryDirectory(prefix="clef-browse-test-chrome-")
    process = subprocess.Popen(
        [
            binary,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile.name}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-extensions",
            *(["--no-sandbox"] if os.environ.get("CI") else []),
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            profile.cleanup()
            _unavailable("Headless Chrome exited before its debugging endpoint became available")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    else:
        _stop(process)
        profile.cleanup()
        _unavailable("Headless Chrome debugging endpoint did not become ready")
    yield url
    _stop(process)
    profile.cleanup()
