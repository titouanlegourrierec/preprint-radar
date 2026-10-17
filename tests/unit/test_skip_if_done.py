"""The data workflows' guard, which stops a fallback scheduled run once the day's run is done.

It also stops every scheduled run in a fork (CI-11), which must not crawl arXiv daily.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / ".github" / "scripts" / "skip-if-done.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None or shutil.which("jq") is None, reason="needs bash and jq")

# Stands in for the GitHub CLI: records each command's arguments and prints what the test
# asks for, whether the repository is a fork for `gh api`, a count of runs for `gh run`.
FAKE_GH = """#!/bin/sh
if [ "$1" = api ]; then
  printf '%s\\n' "$@" > "$FAKE_GH_API_ARGS"
  if [ -n "$FAKE_GH_API_FAIL" ]; then exit 1; fi
  printf '%s\\n' "$FAKE_GH_FORK"
  exit 0
fi
printf '%s\\n' "$@" > "$FAKE_GH_ARGS"
if [ -n "$FAKE_GH_FAIL" ]; then exit 1; fi
printf '%s\\n' "$FAKE_GH_PRINTS"
"""

# The event payload of this repository's runs, which says it is no fork.
NOT_A_FORK = {"repository": {"fork": False}}
A_FORK = {"repository": {"fork": True}}
# The payload of a scheduled run, should it not carry the repository.
SCHEDULE_ONLY = {"schedule": "17 10 * * 1-5"}


@dataclass(frozen=True)
class Guard:
    returncode: int
    output: dict[str, str]
    log: str
    gh_args: list[str] | None
    api_args: list[str] | None


@pytest.fixture
def run_guard(tmp_path: Path) -> Callable[..., Guard]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH, encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    args_file = tmp_path / "gh-args"
    api_args_file = tmp_path / "gh-api-args"
    event_file = tmp_path / "event.json"
    output = tmp_path / "output"

    def run(
        event: str,
        *,
        prints: str = "0",
        fail: bool = False,
        payload: Mapping[str, object] | str | None = NOT_A_FORK,
        api_fork: str | None = "false",
        days_back: str | None = None,
    ) -> Guard:
        """Run the guard for ``event``.

        ``payload`` is the event's payload (raw text if a string, no file if None), and
        ``api_fork`` what the API says of the repository's ``fork`` (None: the call fails), and
        ``days_back`` the script's second argument, if any.
        """
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
            "FAKE_GH_API_ARGS": str(api_args_file),
            "FAKE_GH_FORK": api_fork or "",
            "FAKE_GH_API_FAIL": "1" if api_fork is None else "",
        }
        # Set or removed in every case: in Actions, the test run's own payload is there.
        env.pop("GITHUB_EVENT_PATH", None)
        if payload is not None:
            text = payload if isinstance(payload, str) else json.dumps(payload)
            event_file.write_text(text, encoding="utf-8")
            env["GITHUB_EVENT_PATH"] = str(event_file)
        # A fixed script with fixed arguments.
        result = subprocess.run(  # noqa: S603
            [BASH, str(SCRIPT), "update.yml", *([days_back] if days_back is not None else [])],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        lines = output.read_text(encoding="utf-8").splitlines()
        return Guard(
            result.returncode,
            dict(line.split("=", 1) for line in lines),
            result.stdout,
            _lines(args_file),
            _lines(api_args_file),
        )

    return run


def _lines(path: Path) -> list[str] | None:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else None


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


@pytest.mark.parametrize(("prints", "run"), [("1", "false"), ("0", "true")], ids=["done", "not done"])
def test_a_catch_up_stops_after_a_successful_run_of_the_last_days(
    run_guard: Callable[..., Guard], prints: str, run: str
) -> None:
    # The archive's Saturday catch-up, back to Sunday (CI-8).
    guard = run_guard("schedule", prints=prints, days_back="6")

    assert guard.returncode == 0
    assert guard.output == {"run": run}
    sunday = (datetime.now(UTC) - timedelta(days=6)).date().isoformat()
    assert guard.gh_args is not None
    assert f">={sunday}" in guard.gh_args
    assert (
        f"::notice title=Already done this week::A run of update.yml succeeded since {sunday}" in guard.log
    ) == (run == "false")


def test_a_scheduled_run_goes_on_without_a_successful_run_today(run_guard: Callable[..., Guard]) -> None:
    guard = run_guard("schedule", prints="0")

    assert guard.returncode == 0
    assert guard.output == {"run": "true"}
    assert "::notice" not in guard.log
    # The payload said it is no fork: the API was not asked.
    assert guard.api_args is None


def test_a_scheduled_run_goes_on_when_the_history_cannot_be_read(run_guard: Callable[..., Guard]) -> None:
    guard = run_guard("schedule", fail=True)

    assert guard.returncode == 0
    assert guard.output == {"run": "true"}
    assert "::warning title=Run history unavailable::" in guard.log


def test_a_scheduled_run_in_a_fork_stops(run_guard: Callable[..., Guard]) -> None:
    guard = run_guard("schedule", payload=A_FORK, api_fork=None)

    assert guard.returncode == 0
    assert guard.output == {"run": "false"}
    assert "::notice title=Fork::owner/preprint-radar is a fork, so this scheduled run stops" in guard.log
    assert guard.gh_args is None
    assert guard.api_args is None


def test_a_dispatched_run_in_a_fork_goes_on(run_guard: Callable[..., Guard]) -> None:
    guard = run_guard("workflow_dispatch", payload=A_FORK)

    assert guard.returncode == 0
    assert guard.output == {"run": "true"}
    assert "::notice" not in guard.log
    assert guard.gh_args is None
    assert guard.api_args is None


@pytest.mark.parametrize(
    "payload", [SCHEDULE_ONLY, None, "{not json"], ids=["without the repository", "no file", "unreadable"]
)
def test_the_api_says_it_is_a_fork_when_the_payload_does_not(
    run_guard: Callable[..., Guard], payload: Mapping[str, object] | str | None
) -> None:
    guard = run_guard("schedule", payload=payload, api_fork="true")

    assert guard.returncode == 0
    assert guard.output == {"run": "false"}
    assert "::notice title=Fork::" in guard.log
    assert guard.api_args == ["api", "repos/owner/preprint-radar", "--jq", ".fork"]
    assert guard.gh_args is None


@pytest.mark.parametrize("api_fork", ["false", None], ids=["no fork", "the API fails"])
def test_a_repository_neither_says_is_a_fork_is_not_one(
    run_guard: Callable[..., Guard], api_fork: str | None
) -> None:
    guard = run_guard("schedule", prints="1", payload=SCHEDULE_ONLY, api_fork=api_fork)

    assert guard.returncode == 0
    assert guard.output == {"run": "false"}
    assert "::notice title=Already done today::" in guard.log
    assert "::notice title=Fork::" not in guard.log
    assert guard.api_args is not None
    assert guard.gh_args is not None
