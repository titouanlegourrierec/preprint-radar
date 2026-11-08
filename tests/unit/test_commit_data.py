"""The workflows' data commit script, run against local git repositories."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / ".github" / "scripts" / "commit-data.sh"
GITIGNORE = Path(__file__).parents[2] / ".gitignore"
GIT = shutil.which("git")
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(GIT is None or BASH is None, reason="needs git and bash")

# Stands in for `uv run --no-dev preprint-radar index`, which test_cli covers; it records the
# GH_TOKEN it was given where UV_SAW says.
FAKE_UV = (
    "#!/bin/sh\n"
    'if [ -n "$UV_SAW" ]; then printf %s "${GH_TOKEN:-}" > "$UV_SAW"; fi\n'
    'case "$*" in *validate*) printf "%s\\n" "$*" >> "$UV_VALIDATED"; exit "${UV_INVALID:-0}" ;; esac\n'
    "printf '{\"rewritten\": true}\\n' > data/index.json\n"
)
# The retries' waits, which the tests skip.
FAKE_SLEEP = "#!/bin/sh\nexit 0\n"
DAY = "data/cs.CV/2026-09-28.json"
CITATIONS = "data/cs.CV/citations.json"
INDEX = "data/index.json"
# On the data branch (SCALE-8).
GAINS = "data/cs.CV/citation-gains.json"
ARCHIVE = "data/cs.CV/archive/2024.json"
BRANCH = ".data-branch"
OLD = "2000-01-01T00:00:00+00:00"


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


def _git(repos: Repos, cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    assert GIT is not None
    result = _run([GIT, *args], cwd, env or repos.env)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _write(repo: Path, path: str, payload: object) -> None:
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _read(repo: Path, path: str) -> object:
    return json.loads((repo / path).read_text(encoding="utf-8"))


def _commit_and_push(repos: Repos, repo: Path, changes: dict[str, object], branch: str = "main") -> None:
    """A commit of `repo` (a clone of main, or of the data branch) pushed to `branch`."""
    for path, payload in changes.items():
        _write(repo, path, payload)
    _git(repos, repo, "add", "-A")
    _git(repos, repo, "commit", "--quiet", "-m", "chore(data): by hand")
    _git(repos, repo, "push", "--quiet", "origin", f"HEAD:{branch}")


def _commit_data(
    repos: Repos, *options: str, env: dict[str, str] | None = None
) -> tuple[int, dict[str, str]]:
    assert BASH is not None
    result = _run([BASH, str(SCRIPT), *options, "chore(data): update"], repos.bot, env or repos.env)
    lines = repos.output.read_text(encoding="utf-8").splitlines() if repos.output.exists() else []
    return result.returncode, dict(line.split("=", 1) for line in lines)


def _data_commits(repos: Repos) -> int:
    return int(_git(repos, repos.origin, "rev-list", "--count", "data"))


def _repos(tmp_path: Path, data_since: str | None = None) -> Repos:
    """main and the data branch on an origin, cloned as the workflows check them out."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, script in (("uv", FAKE_UV), ("sleep", FAKE_SLEEP)):
        (bin_dir / name).write_text(script, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    env = {
        # A token in the shell would reach the script.
        **{name: value for name, value in os.environ.items() if name != "GH_TOKEN"},
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "UV_VALIDATED": str(tmp_path / "validated"),
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
    shutil.copy(GITIGNORE, repos.maintainer / ".gitignore")
    _commit_and_push(repos, repos.maintainer, {INDEX: {"days": 1}, DAY: {"papers": []}, CITATIONS: {}})
    # The data branch, its first commit of `data_since`.
    branch = repos.maintainer / BRANCH
    _git(repos, tmp_path, "init", "--quiet", "--initial-branch=data", str(branch))
    _git(repos, branch, "remote", "add", "origin", str(repos.origin))
    _write(branch, ARCHIVE, {"papers": []})
    _write(branch, GAINS, {})
    _git(repos, branch, "add", "-A")
    dated = {**env, "GIT_COMMITTER_DATE": data_since} if data_since else env
    _git(repos, branch, "commit", "--quiet", "-m", "chore(data): the data branch", env=dated)
    _git(repos, branch, "push", "--quiet", "origin", "HEAD:data")
    # The workflows' two checkouts, the data branch's in .data-branch/, then data/ assembled.
    _git(repos, tmp_path, "clone", "--quiet", str(repos.origin), str(repos.bot))
    _git(repos, tmp_path, "clone", "--quiet", "--branch", "data", str(repos.origin), str(repos.bot / BRANCH))
    for path in (ARCHIVE, GAINS):
        _write(repos.bot, path, _read(repos.bot / BRANCH, path))
    return repos


@pytest.fixture
def repos(tmp_path: Path) -> Repos:
    return _repos(tmp_path)


def test_does_nothing_without_new_data(repos: Repos) -> None:
    assert _commit_data(repos) == (0, {"pushed": "false"})


def test_commits_the_archives_files_to_the_data_branch_and_the_others_to_main(repos: Repos) -> None:
    _write(repos.bot, ARCHIVE, {"papers": ["cited"]})
    _write(repos.bot, DAY, {"papers": ["new"]})

    assert _commit_data(repos) == (0, {"pushed": "true"})
    assert json.loads(_git(repos, repos.origin, "show", f"data:{ARCHIVE}")) == {"papers": ["cited"]}
    assert json.loads(_git(repos, repos.origin, "show", f"main:{DAY}")) == {"papers": ["new"]}
    assert ARCHIVE not in _git(repos, repos.origin, "ls-tree", "-r", "--name-only", "main")
    assert DAY not in _git(repos, repos.origin, "ls-tree", "-r", "--name-only", "data")


def test_a_change_to_the_data_branch_alone_is_pushed(repos: Repos) -> None:
    main_before = _git(repos, repos.origin, "rev-parse", "main")
    _write(repos.bot, ARCHIVE, {"papers": ["cited"]})

    assert _commit_data(repos) == (0, {"pushed": "true"})
    assert _git(repos, repos.origin, "rev-parse", "main") == main_before
    assert _data_commits(repos) == 2


def test_stops_without_a_checkout_of_the_data_branch(repos: Repos) -> None:
    shutil.rmtree(repos.bot / BRANCH)
    _write(repos.bot, DAY, {"papers": ["new"]})

    assert _commit_data(repos)[0] == 1
    assert _read(repos.maintainer, DAY) == {"papers": []}


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


def test_the_token_reaches_git_alone_and_is_never_stored(repos: Repos, tmp_path: Path) -> None:
    # The checkouts keep no credentials: the push token is the script's, for git only (PUB-2).
    _commit_and_push(repos, repos.maintainer, {INDEX: {"days": 2}})
    _write(repos.bot, INDEX, {"days": 3})
    _write(repos.bot, DAY, {"papers": ["new"]})
    _write(repos.bot, ARCHIVE, {"papers": ["cited"]})
    seen = tmp_path / "uv-saw"
    env = {**repos.env, "GH_TOKEN": "made-up-token", "UV_SAW": str(seen)}

    assert _commit_data(repos, env=env) == (0, {"pushed": "true"})
    assert seen.read_text(encoding="utf-8") == ""
    for config in (repos.bot / ".git" / "config", repos.bot / BRANCH / ".git" / "config"):
        assert "made-up-token" not in config.read_text(encoding="utf-8")


def test_keeps_this_runs_citation_counts_and_gains_on_a_conflict(repos: Repos) -> None:
    _commit_and_push(repos, repos.maintainer, {CITATIONS: {"2609.00001": 1}})
    _commit_and_push(repos, repos.maintainer / BRANCH, {GAINS: {"2609.00001": 1}}, branch="data")
    _write(repos.bot, CITATIONS, {"2609.00002": 2})
    _write(repos.bot, GAINS, {"2609.00002": 1})

    assert _commit_data(repos) == (0, {"pushed": "true"})
    assert json.loads(_git(repos, repos.origin, "show", f"main:{CITATIONS}")) == {"2609.00002": 2}
    assert json.loads(_git(repos, repos.origin, "show", f"data:{GAINS}")) == {"2609.00002": 1}


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


def test_stops_on_a_conflict_in_an_archive_file_and_pushes_neither_branch(repos: Repos) -> None:
    _commit_and_push(repos, repos.maintainer / BRANCH, {ARCHIVE: {"papers": ["by hand"]}}, branch="data")
    main_before = _git(repos, repos.origin, "rev-parse", "main")
    _write(repos.bot, ARCHIVE, {"papers": ["new"]})
    _write(repos.bot, DAY, {"papers": ["new"]})

    assert _commit_data(repos) == (1, {"pushed": "false"})
    assert _git(repos, repos.origin, "rev-parse", "main") == main_before
    assert json.loads(_git(repos, repos.origin, "show", f"data:{ARCHIVE}")) == {"papers": ["by hand"]}
    # Fetched back where the data branch is.
    data_clone = repos.maintainer / BRANCH
    _git(repos, data_clone, "fetch", "--quiet", str(repos.bot / "data-branch.bundle"), "HEAD:recovered")
    assert json.loads(_git(repos, data_clone, "show", f"recovered:{ARCHIVE}")) == {"papers": ["new"]}
    assert (repos.bot / "data-commit.bundle").exists()


def test_a_refused_main_keeps_the_data_branch_pushed_first(repos: Repos) -> None:
    # main refuses every push: the data branch, pushed first, holds the run's archive.
    hook = repos.origin / "hooks" / "pre-receive"
    hook.write_text('#!/bin/sh\ngrep -q " refs/heads/main$" && exit 1\nexit 0\n', encoding="utf-8")
    hook.chmod(0o755)
    _write(repos.bot, ARCHIVE, {"papers": ["cited"]})
    _write(repos.bot, DAY, {"papers": ["new"]})

    assert _commit_data(repos) == (1, {"pushed": "true"})
    assert json.loads(_git(repos, repos.origin, "show", f"data:{ARCHIVE}")) == {"papers": ["cited"]}
    assert (repos.bot / "data-commit.bundle").exists()
    assert not (repos.bot / "data-branch.bundle").exists()


def test_keep_saves_the_commits_without_pushing(repos: Repos) -> None:
    main_before = _git(repos, repos.origin, "rev-parse", "main")
    _write(repos.bot, DAY, {"papers": ["not validated"]})
    _write(repos.bot, ARCHIVE, {"papers": ["not validated"]})

    assert _commit_data(repos, "--keep") == (0, {"pushed": "false"})
    assert _git(repos, repos.origin, "rev-parse", "main") == main_before
    assert _data_commits(repos) == 1
    _git(repos, repos.maintainer, "fetch", "--quiet", str(repos.bot / "data-commit.bundle"), "HEAD:recovered")
    assert (
        _git(repos, repos.maintainer, "show", f"recovered:{DAY}").strip() == '{"papers": ["not validated"]}'
    )
    data_clone = repos.maintainer / BRANCH
    _git(repos, data_clone, "fetch", "--quiet", str(repos.bot / "data-branch.bundle"), "HEAD:recovered")
    assert json.loads(_git(repos, data_clone, "show", f"recovered:{ARCHIVE}")) == {
        "papers": ["not validated"]
    }


def test_squashes_the_data_branch_begun_before_this_month(tmp_path: Path) -> None:
    repos = _repos(tmp_path, data_since=OLD)
    _write(repos.bot, ARCHIVE, {"papers": ["cited"]})

    assert _commit_data(repos, "--squash-monthly") == (0, {"pushed": "true"})
    # One commit, of the tree just pushed.
    assert _data_commits(repos) == 1
    assert json.loads(_git(repos, repos.origin, "show", f"data:{ARCHIVE}")) == {"papers": ["cited"]}
    assert "squashed" in _git(repos, repos.origin, "log", "-1", "--format=%s", "data")


def test_squashes_even_a_week_without_new_data(tmp_path: Path) -> None:
    repos = _repos(tmp_path, data_since=OLD)

    assert _commit_data(repos, "--squash-monthly") == (0, {"pushed": "false"})
    assert _git(repos, repos.origin, "log", "-1", "--format=%cs", "data").strip() > OLD[:10]


def test_keeps_the_data_branch_begun_this_month(repos: Repos) -> None:
    _write(repos.bot, ARCHIVE, {"papers": ["cited"]})

    assert _commit_data(repos, "--squash-monthly") == (0, {"pushed": "true"})
    assert _data_commits(repos) == 2


def test_squashes_only_when_asked(tmp_path: Path) -> None:
    repos = _repos(tmp_path, data_since=OLD)
    _write(repos.bot, ARCHIVE, {"papers": ["cited"]})

    assert _commit_data(repos) == (0, {"pushed": "true"})
    assert _data_commits(repos) == 2


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


def test_validate_summarizes_only_the_warnings_new_to_the_run(tmp_path: Path) -> None:
    assert BASH is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    report = "WARNING data/cs.CV/scholar.json: stale\nWARNING data/cs.CV/2026-11-02.json: new\ncounts\n"
    (bin_dir / "uv").write_text(f"#!/bin/sh\nprintf '{report}'\n", encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    known = tmp_path / "known.txt"
    known.write_text("WARNING data/cs.CV/scholar.json: stale\nold counts\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_STEP_SUMMARY": str(summary),
        "KNOWN_WARNINGS": str(known),
    }

    result = _run([BASH, str(VALIDATE_SCRIPT)], tmp_path, env)

    # The log keeps every finding; the summary, those new to the run (OPS-11).
    assert "stale" in result.stdout
    written = summary.read_text(encoding="utf-8")
    assert "stale" not in written
    assert "WARNING data/cs.CV/2026-11-02.json: new" in written
    assert "And 1 warnings known before this run, in the step log." in written


def test_validate_passes_its_options_on(tmp_path: Path) -> None:
    assert BASH is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uv").write_text('#!/bin/sh\necho "$@"\n', encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    env.pop("GITHUB_STEP_SUMMARY", None)

    result = _run([BASH, str(VALIDATE_SCRIPT), "--set-aside"], tmp_path, env)

    assert result.stdout == "run --no-dev preprint-radar validate --set-aside\n"


def test_validates_the_commit_replayed_on_a_main_that_moved(repos: Repos, tmp_path: Path) -> None:
    _write(repos.bot, DAY, {"papers": ["new"]})
    assert _commit_data(repos) == (0, {"pushed": "true"})
    # main did not move: what validate-data.sh checked is what was pushed.
    assert not (tmp_path / "validated").exists()

    _git(repos, repos.maintainer, "pull", "--quiet")
    _commit_and_push(repos, repos.maintainer, {"README.md": "a change elsewhere"})
    _write(repos.bot, DAY, {"papers": ["newer"]})
    assert _commit_data(repos) == (0, {"pushed": "true"})
    assert (tmp_path / "validated").read_text(encoding="utf-8").split() == [
        "run",
        "--no-dev",
        "preprint-radar",
        "validate",
    ]


def test_validates_the_data_replayed_on_a_data_branch_that_moved(repos: Repos, tmp_path: Path) -> None:
    other = "data/cs.CV/archive/2023.json"
    _commit_and_push(repos, repos.maintainer / BRANCH, {other: {"papers": ["by hand"]}}, branch="data")
    _write(repos.bot, ARCHIVE, {"papers": ["cited"]})

    assert _commit_data(repos) == (0, {"pushed": "true"})
    assert (tmp_path / "validated").exists()
    # Validated over data/ as the branch now holds it.
    assert _read(repos.bot, other) == {"papers": ["by hand"]}


def test_keeps_a_replayed_commit_that_does_not_validate(repos: Repos) -> None:
    _commit_and_push(repos, repos.maintainer, {"README.md": "a change elsewhere"})
    _write(repos.bot, DAY, {"papers": ["new"]})

    assert _commit_data(repos, env={**repos.env, "UV_INVALID": "1"}) == (1, {"pushed": "false"})
    assert (repos.bot / "data-commit.bundle").exists()
    _git(repos, repos.maintainer, "pull", "--quiet")
    assert _read(repos.maintainer, DAY) == {"papers": []}
