"""The data workflows' guard, which stops a fallback scheduled run once the day's run is done."""

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / ".github" / "scripts" / "skip-if-done.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")

# Stands in for the GitHub CLI: records its arguments, prints what the test asks for.
FAKE_GH = """#!/bin/sh
printf '%s\\n' "$@" > "$FAKE_GH_ARGS"
if [ -n "$FAKE_GH_FAIL" ]; then exit 1; fi
printf '%s\\n' "$FAKE_GH_PRINTS"
"""


@dataclass(frozen=True)
class Guard:
    returncode: int
    output: dict[str, str]
    log: str
    gh_args: list[str] | None


@pytest.fixture
def run_guard(tmp_path: Path) -> Callable[..., Guard]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH, encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    args_file = tmp_path / "gh-args"
    output = tmp_path / "output"

    def run(event: str, *, prints: str = "0", fail: bool = False) -> Guard:
        assert BASH is not None
        env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "owner/preprint-radar",
            "GITHUB_EVENT_NAME": event,
            "FAKE_GH_ARGS": str(args_file),
            "FAKE_GH_PRINTS": prints,
            "FAKE_GH_FAIL": "1" if fail else "",
        }
        # A fixed script with fixed arguments.
        result = subprocess.run(  # noqa: S603
            [BASH, str(SCRIPT), "update.yml"], env=env, capture_output=True, text=True, check=False
        )
        lines = output.read_text(encoding="utf-8").splitlines()
        gh_args = args_file.read_text(encoding="utf-8").splitlines() if args_file.exists() else None
        return Guard(result.returncode, dict(line.split("=", 1) for line in lines), result.stdout, gh_args)

    return run


def test_a_dispatched_run_always_goes_on(run_guard: Callable[..., Guard]) -> None:
    guard = run_guard("workflow_dispatch", prints="1")

    assert guard.returncode == 0
    assert guard.output == {"run": "true"}
    assert guard.gh_args is None


def test_a_scheduled_run_stops_after_a_successful_run_today(run_guard: Callable[..., Guard]) -> None:
    guard = run_guard("schedule", prints="1")

    assert guard.returncode == 0
    assert guard.output == {"run": "false"}
    assert "::notice title=Already done today::" in guard.log
    assert guard.gh_args is not None
    today = datetime.now(UTC).date().isoformat()
    assert f">={today}" in guard.gh_args
    for flag, value in [
        ("--workflow", "update.yml"),
        ("--status", "success"),
        ("--repo", "owner/preprint-radar"),
    ]:
        assert guard.gh_args[guard.gh_args.index(flag) + 1] == value


def test_a_scheduled_run_goes_on_without_a_successful_run_today(run_guard: Callable[..., Guard]) -> None:
    guard = run_guard("schedule", prints="0")

    assert guard.returncode == 0
    assert guard.output == {"run": "true"}
    assert "::notice" not in guard.log


def test_a_scheduled_run_goes_on_when_the_history_cannot_be_read(run_guard: Callable[..., Guard]) -> None:
    guard = run_guard("schedule", fail=True)

    assert guard.returncode == 0
    assert guard.output == {"run": "true"}
    assert "::warning title=Run history unavailable::" in guard.log
