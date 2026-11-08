"""The data branch's script (SCALE-8), run against local git repositories, and its users."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "data-branch.sh"
GIT = shutil.which("git")
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(GIT is None or BASH is None, reason="needs git and bash")

ARCHIVE = "data/cs.CV/archive/2024.json"
OLD_YEAR = "data/cs.CV/archive/2010.json"
TOP = "data/cs.CV/top-recent.json"
DAY = "data/cs.CV/2026-09-28.json"
BRANCH = ".data-branch"
ENV = {
    **{name: value for name, value in os.environ.items() if name not in {"GH_TOKEN", "FORCE"}},
    # Neither the user's git configuration (signing, hooks...) nor the system's.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Maintainer",
    "GIT_AUTHOR_EMAIL": "maintainer@example.org",
    "GIT_COMMITTER_NAME": "Maintainer",
    "GIT_COMMITTER_EMAIL": "maintainer@example.org",
}


def _run(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    # Fixed commands on temporary repositories.
    return subprocess.run(command, cwd=cwd, env=env or ENV, capture_output=True, text=True, check=False)  # noqa: S603


def _git(cwd: Path, *args: str) -> str:
    assert GIT is not None
    result = _run([GIT, *args], cwd)
    assert result.returncode == 0, result.stderr
    return result.stdout


# Stands in for the GitHub CLI, which would dispatch a real workflow: it records its arguments.
FAKE_GH = '#!/bin/sh\necho "$@" >> "$(dirname "$0")/gh-calls"\n'


def _script(cwd: Path, *args: str, force: bool = False) -> subprocess.CompletedProcess[str]:
    """The script run in the clone `cwd`, the fake gh of its tmp_path's bin/ first on the path."""
    assert BASH is not None
    env = {**ENV, "PATH": f"{cwd.parent / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    if force:
        env["FORCE"] = "1"
    return _run([BASH, str(SCRIPT), *args], cwd, env)


def _write(repo: Path, path: str, payload: object) -> None:
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _read(repo: Path, path: str) -> object:
    return json.loads((repo / path).read_text(encoding="utf-8"))


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A maintainer's clone of main, beside an origin that holds the data branch."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "--quiet", "--initial-branch=data", str(seed))
    _write(seed, ARCHIVE, {"papers": ["cited"]})
    _write(seed, OLD_YEAR, {"papers": []})
    _write(seed, TOP, {"papers": []})
    _git(seed, "add", "-A")
    _git(seed, "commit", "--quiet", "-m", "data")
    _git(seed, "push", "--quiet", str(origin), "HEAD:data")
    _git(seed, "checkout", "--quiet", "--orphan", "main")
    _git(seed, "rm", "--quiet", "-rf", ".")
    shutil.copy(ROOT / ".gitignore", seed / ".gitignore")
    _write(seed, DAY, {"papers": []})
    _git(seed, "add", "-A")
    _git(seed, "commit", "--quiet", "-m", "main")
    _git(seed, "push", "--quiet", str(origin), "HEAD:main")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "gh").write_text(FAKE_GH, encoding="utf-8")
    (tmp_path / "bin" / "gh").chmod(0o755)
    return clone


def test_gitignore_lists_the_data_branchs_paths() -> None:
    paths = re.search(r"^PATHS=\((.+)\)$", SCRIPT.read_text(encoding="utf-8"), re.MULTILINE)
    assert paths is not None
    ignored = re.findall(
        r"^/data/\*/(.+?)/?$", (ROOT / ".gitignore").read_text(encoding="utf-8"), re.MULTILINE
    )
    assert ignored == paths.group(1).split()


def test_pull_checks_the_branch_out_and_copies_it_into_data(clone: Path) -> None:
    assert _script(clone, "check").returncode == 1

    assert _script(clone, "pull").returncode == 0
    assert _read(clone, ARCHIVE) == {"papers": ["cited"]}
    assert _script(clone, "check").returncode == 0
    # Ignored on main: nothing to commit there.
    assert _git(clone, "status", "--porcelain") == ""


def test_check_fails_when_data_lacks_a_file_of_the_branch(clone: Path) -> None:
    _script(clone, "pull")
    (clone / TOP).unlink()

    result = _script(clone, "check")
    assert result.returncode == 1
    assert "make data-pull" in result.stderr


def test_assemble_drops_what_the_branch_no_longer_holds(clone: Path) -> None:
    _script(clone, "pull")
    (clone / BRANCH / OLD_YEAR).unlink()
    _write(clone / BRANCH, ARCHIVE, {"papers": ["newer"]})

    assert _script(clone, "assemble").returncode == 0
    assert not (clone / OLD_YEAR).exists()
    assert _read(clone, ARCHIVE) == {"papers": ["newer"]}
    assert _read(clone, DAY) == {"papers": []}


def test_assemble_and_collect_need_the_branch(clone: Path) -> None:
    for command in ("assemble", "collect", "check"):
        result = _script(clone, command)
        assert result.returncode == 1
        assert "holds no checkout of the data branch" in result.stderr


def test_commit_puts_each_file_on_its_branch(clone: Path) -> None:
    _script(clone, "pull")
    _write(clone, ARCHIVE, {"papers": ["by hand"]})
    _write(clone, DAY, {"papers": ["by hand"]})
    # Staged beside, and left out of the data commit.
    (clone / "README.md").write_text("unrelated\n", encoding="utf-8")
    _git(clone, "add", "README.md")

    assert _script(clone, "commit", "fix(data): by hand").returncode == 0
    assert _git(clone / BRANCH, "log", "-1", "--format=%s").strip() == "fix(data): by hand"
    assert json.loads(_git(clone / BRANCH, "show", f"HEAD:{ARCHIVE}")) == {"papers": ["by hand"]}
    assert _git(clone, "show", "--name-only", "--format=", "HEAD").split() == [DAY]
    assert _git(clone, "status", "--porcelain").strip() == "A  README.md"


def test_push_sends_the_data_branch_then_main(clone: Path) -> None:
    _script(clone, "pull")
    _write(clone, ARCHIVE, {"papers": ["by hand"]})
    _write(clone, DAY, {"papers": ["by hand"]})
    _script(clone, "commit", "fix(data): by hand")

    assert _script(clone, "push").returncode == 0
    assert json.loads(_git(clone, "show", f"origin/data:{ARCHIVE}")) == {"papers": ["by hand"]}
    assert json.loads(_git(clone, "show", f"origin/main:{DAY}")) == {"papers": ["by hand"]}
    # main's push of data/ deploys by itself.
    assert not (clone.parent / "bin" / "gh-calls").exists()


def test_push_of_the_data_branch_alone_dispatches_the_deploy(clone: Path) -> None:
    # The data branch holds no workflow: its push runs none.
    _script(clone, "pull")
    _write(clone, ARCHIVE, {"papers": ["by hand"]})
    _script(clone, "commit", "fix(data): by hand")

    assert _script(clone, "push").returncode == 0
    assert (clone.parent / "bin" / "gh-calls").read_text(encoding="utf-8") == (
        "workflow run deploy.yml --ref main\n"
    )


def test_pull_refuses_changes_not_committed_unless_forced(clone: Path) -> None:
    _script(clone, "pull")
    _write(clone, ARCHIVE, {"papers": ["unsaved"]})

    result = _script(clone, "pull")
    assert result.returncode == 1
    assert "make data-commit" in result.stderr
    assert _read(clone, ARCHIVE) == {"papers": ["unsaved"]}

    assert _script(clone, "pull", force=True).returncode == 0
    assert _read(clone, ARCHIVE) == {"papers": ["cited"]}


def test_pull_refuses_commits_not_pushed(clone: Path) -> None:
    _script(clone, "pull")
    _write(clone, ARCHIVE, {"papers": ["by hand"]})
    _script(clone, "commit", "fix(data): by hand")

    result = _script(clone, "pull")
    assert result.returncode == 1
    assert "make data-push" in result.stderr


def test_pull_follows_a_squashed_branch(clone: Path, tmp_path: Path) -> None:
    _script(clone, "pull")
    # The archive squashes the branch into a new first commit, with the week's archive.
    other = tmp_path / "other"
    _git(tmp_path, "clone", "--quiet", "--branch", "data", str(tmp_path / "origin.git"), str(other))
    _write(other, ARCHIVE, {"papers": ["squashed"]})
    _git(other, "add", "-A")
    tree = _git(other, "write-tree").strip()
    root = _git(other, "commit-tree", tree, "-m", "squashed").strip()
    _git(other, "push", "--quiet", "--force", "origin", f"{root}:refs/heads/data")

    assert _script(clone, "pull").returncode == 0
    assert _read(clone, ARCHIVE) == {"papers": ["squashed"]}
    assert _git(clone / BRANCH, "rev-list", "--count", "HEAD").strip() == "1"


def _jobs(workflow: Path) -> dict[str, str]:
    """Each job's text, by name."""
    text = workflow.read_text(encoding="utf-8")
    jobs = text[text.index("\njobs:\n") :]
    parts = re.split(r"^  ([\w-]+):\n", jobs, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


@pytest.mark.parametrize(
    "workflow", sorted((ROOT / ".github" / "workflows").glob("*.yml")), ids=lambda p: p.name
)
def test_every_job_that_reads_data_assembles_it_first(workflow: Path) -> None:
    # Missing, the archive's files would read as an archive emptied, and be pushed so.
    readers = re.compile(
        r"preprint-radar|validate-data\.sh|commit-data\.sh|vite build|npm run build|npm test"
    )
    for name, job in _jobs(workflow).items():
        # Steps without their comments, which name commit-data.sh.
        steps = [
            "\n".join(line for line in step.splitlines() if not line.lstrip().startswith("#"))
            for step in job.split("\n      - ")
        ]
        first_reader = next((i for i, step in enumerate(steps) if readers.search(step)), None)
        if first_reader is None:
            continue
        assemble = next((i for i, step in enumerate(steps) if "data-branch.sh assemble" in step), None)
        assert assemble is not None, f"{workflow.name}: {name} reads data/ without the data branch"
        assert assemble < first_reader, f"{workflow.name}: {name} reads data/ before assembling it"
