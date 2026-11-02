"""The page cache restored from its weekly copy when the Actions cache had none (OPS-1, SCALE-4)."""

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / ".github" / "scripts" / "restore-page-cache.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None or shutil.which("unzip") is None, reason="needs bash and unzip")

# Stands in for the GitHub CLI: the newest copy's id and day, or none, then its zip.
FAKE_GH = """#!/bin/sh
case "$*" in
  *"/zip"*) cat "$FAKE_GH_ZIP" ;;
  *) printf '%s' "$FAKE_GH_COPY" ;;
esac
"""


def _restore(tmp_path: Path, copy: str) -> tuple[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH, encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    archive = tmp_path / "copy.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("2610/2610.00001v1.html.gz", b"page")
    work = tmp_path / "work"
    (tmp_path / "temp").mkdir()
    work.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_REPOSITORY": "owner/preprint-radar",
        "RUNNER_TEMP": str(tmp_path / "temp"),
        "FAKE_GH_COPY": copy,
        "FAKE_GH_ZIP": str(archive),
    }
    assert BASH is not None
    # A fixed script in a temporary directory.
    result = subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT)], cwd=work, env=env, capture_output=True, text=True, check=True
    )
    return result.stdout, work / ".cache" / "front-matter"


def test_the_weekly_copy_is_restored(tmp_path: Path) -> None:
    out, cache = _restore(tmp_path, "17 2026-11-02T06:40:00Z")

    assert (cache / "2610" / "2610.00001v1.html.gz").read_bytes() == b"page"
    assert (
        "::warning title=Page cache not restored::No cache entry: restored from its weekly copy of 2026-11-02"
        in out
    )


def test_without_a_copy_the_pages_are_downloaded_again(tmp_path: Path) -> None:
    out, cache = _restore(tmp_path, "")

    assert not cache.exists()
    assert "No cache entry nor weekly copy" in out
