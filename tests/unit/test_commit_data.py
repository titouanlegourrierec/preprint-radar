"""The workflows' data commit script, run against local git repositories."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / ".github" / "scripts" / "commit-data.sh"
GIT = shutil.which("git")
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(GIT is None or BASH is None, reason="needs git and bash")

# Stands in for `uv run --no-dev preprint-radar index`, which test_cli covers.
FAKE_UV = "#!/bin/sh\nprintf '{\"rewritten\": true}\\n' > data/index.json\n"
DAY = "data/cs.CV/2026-09-28.json"
CITATIONS = "data/cs.CV/citations.json"
INDEX = "data/index.json"


@dataclass(frozen=True)
class Repos:
    origin: Path
    bot: Path
    maintainer: Path
    env: dict[str, str]
    output: Path


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # Fixed commands on temporary repositories.
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)  # noqa: S603


def _git(repos: Repos, cwd: Path, *args: str) -> str:
    assert GIT is not None
    result = _run([GIT, *args], cwd, repos.env)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _write(repo: Path, path: str, payload: object) -> None:
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _read(repo: Path, path: str) -> object:
    return json.loads((repo / path).read_text(encoding="utf-8"))


def _commit_and_push(repos: Repos, repo: Path, changes: dict[str, object]) -> None:
    for path, payload in changes.items():
        _write(repo, path, payload)
    _git(repos, repo, "add", "-A")
    _git(repos, repo, "commit", "--quiet", "-m", "chore(data): by hand")
    _git(repos, repo, "push", "--quiet", "origin", "HEAD:main")


def _commit_data(repos: Repos, *options: str) -> tuple[int, dict[str, str]]:
    assert BASH is not None
    result = _run([BASH, str(SCRIPT), *options, "chore(data): update"], repos.bot, repos.env)
    lines = repos.output.read_text(encoding="utf-8").splitlines() if repos.output.exists() else []
    return result.returncode, dict(line.split("=", 1) for line in lines)


@pytest.fixture
def repos(tmp_path: Path) -> Repos:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uv").write_text(FAKE_UV, encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        # Neither the user's git configuration (signing, hooks...) nor the system's.
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Maintainer",
        "GIT_AUTHOR_EMAIL": "maintainer@example.org",
        "GIT_COMMITTER_NAME": "Maintainer",
        "GIT_COMMITTER_EMAIL": "maintainer@example.org",
    }
    repos = Repos(
        tmp_path / "origin.git", tmp_path / "bot", tmp_path / "maintainer", env, tmp_path / "output"
    )
    _git(repos, tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(repos.origin))
    _git(repos, tmp_path, "clone", "--quiet", str(repos.origin), str(repos.maintainer))
    _commit_and_push(repos, repos.maintainer, {INDEX: {"days": 1}, DAY: {"papers": []}, CITATIONS: {}})
    _git(repos, tmp_path, "clone", "--quiet", str(repos.origin), str(repos.bot))
    return repos


def test_does_nothing_without_new_data(repos: Repos) -> None:
    assert _commit_data(repos) == (0, {"pushed": "false"})


def test_replays_the_commit_on_a_main_that_moved(repos: Repos) -> None:
    _commit_and_push(repos, repos.maintainer, {"README.md": "a change elsewhere"})
    _write(repos.bot, DAY, {"papers": ["new"]})

    assert _commit_data(repos) == (0, {"pushed": "true"})
    _git(repos, repos.maintainer, "pull", "--quiet")
    assert _read(repos.maintainer, DAY) == {"papers": ["new"]}
    assert (repos.maintainer / "README.md").exists()


def test_writes_the_index_again_on_a_conflict(repos: Repos) -> None:
    _commit_and_push(repos, repos.maintainer, {INDEX: {"days": 2}, "data/cs.CV/2026-09-25.json": {}})
    _write(repos.bot, INDEX, {"days": 3})
    _write(repos.bot, DAY, {"papers": ["new"]})

    assert _commit_data(repos) == (0, {"pushed": "true"})
    _git(repos, repos.maintainer, "pull", "--quiet")
    assert _read(repos.maintainer, INDEX) == {"rewritten": True}
    assert _read(repos.maintainer, DAY) == {"papers": ["new"]}
    assert (repos.maintainer / "data/cs.CV/2026-09-25.json").exists()


def test_keeps_this_runs_citation_counts_on_a_conflict(repos: Repos) -> None:
    _commit_and_push(repos, repos.maintainer, {CITATIONS: {"2609.00001": 1}})
    _write(repos.bot, CITATIONS, {"2609.00002": 2})

    assert _commit_data(repos) == (0, {"pushed": "true"})
    _git(repos, repos.maintainer, "pull", "--quiet")
    assert _read(repos.maintainer, CITATIONS) == {"2609.00002": 2}


def test_stops_on_a_conflict_in_a_day_file_and_keeps_the_commit(repos: Repos) -> None:
    _commit_and_push(repos, repos.maintainer, {DAY: {"papers": ["by hand"]}})
    main_before = _git(repos, repos.origin, "rev-parse", "main")
    _write(repos.bot, DAY, {"papers": ["new"]})

    assert _commit_data(repos) == (1, {"pushed": "false"})
    assert _git(repos, repos.origin, "rev-parse", "main") == main_before
    assert not (repos.bot / ".git" / "rebase-merge").exists()
    # The bundle holds this run's commit, ready to be fetched back.
    _git(repos, repos.maintainer, "fetch", "--quiet", str(repos.bot / "data-commit.bundle"), "HEAD:recovered")
    assert (
        _git(repos, repos.maintainer, "log", "-1", "--format=%s", "recovered").strip()
        == "chore(data): update"
    )


def test_keep_saves_the_commit_without_pushing(repos: Repos) -> None:
    main_before = _git(repos, repos.origin, "rev-parse", "main")
    _write(repos.bot, DAY, {"papers": ["not validated"]})

    assert _commit_data(repos, "--keep") == (0, {"pushed": "false"})
    assert _git(repos, repos.origin, "rev-parse", "main") == main_before
    _git(repos, repos.maintainer, "fetch", "--quiet", str(repos.bot / "data-commit.bundle"), "HEAD:recovered")
    assert (
        _git(repos, repos.maintainer, "show", f"recovered:{DAY}").strip() == '{"papers": ["not validated"]}'
    )


VALIDATE_SCRIPT = SCRIPT.with_name("validate-data.sh")


@pytest.mark.parametrize(("lines", "status"), [(3, 0), (150, 1)])
def test_validate_copies_its_report_into_the_job_summary(tmp_path: Path, lines: int, status: int) -> None:
    assert BASH is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Stands in for `uv run --no-dev preprint-radar validate`: findings, then the counts.
    (bin_dir / "uv").write_text(
        f'#!/bin/sh\nfor i in $(seq {lines - 1}); do echo "WARNING finding $i"; done\n'
        f"echo counts\nexit {status}\n",
        encoding="utf-8",
    )
    (bin_dir / "uv").chmod(0o755)
    summary = tmp_path / "summary.md"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_STEP_SUMMARY": str(summary),
    }

    result = _run([BASH, str(VALIDATE_SCRIPT)], tmp_path, env)

    assert result.returncode == status
    assert len(result.stdout.splitlines()) == lines
    written = summary.read_text(encoding="utf-8").splitlines()
    assert written[:3] == ["### Data validation", "", "```"]
    assert written[-2:] == ["counts", "```"]
    # Past 100 lines: the first 99 findings, a line saying how many more, then the counts.
    assert len(written) == 4 + (lines if lines <= 100 else 101)
