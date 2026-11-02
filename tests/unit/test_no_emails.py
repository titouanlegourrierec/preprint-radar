"""No real e-mail address in the code, the tests or the docs (CI-13, PUB-4).

Pages quoted as evidence keep their domain, the mailbox becomes ``author``; ``data/`` holds
what arXiv publishes, which ``validate`` checks, and the audits are frozen snapshots.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCANNED = ("src", "tests", "docs", "web/src", "web/tooling", "web/tests", "web/e2e", ".github")
SKIPPED = ("docs/audit/", "web/e2e/data/")
ROOT_FILES = ("README.md", "CLAUDE.md", "CHANGELOG.md", "SECURITY.md", "Makefile", "pyproject.toml")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")
_CONTACT_RE = re.compile(r'CONTACT_EMAIL = "([^"]+)"')


def _contact() -> str:
    match = _CONTACT_RE.search((ROOT / "web" / "src" / "report.ts").read_text(encoding="utf-8"))
    assert match is not None
    return match.group(1)


def _allowed(address: str, contact: str) -> bool:
    local, _, domain = address.partition("@")
    return (
        # A glued mailbox keeps the word before it: "Oxfordauthor@robots.ox.ac.uk".
        local.endswith("author")
        or address == contact
        or re.fullmatch(r"example\.[a-z]+", domain) is not None
        or domain == "arxiv.org"
    )


def _files() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    for directory in SCANNED:
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file())
    return [
        path
        for path in files
        if not path.relative_to(ROOT).as_posix().startswith(SKIPPED) and "__pycache__" not in path.parts
    ]


def test_no_real_email_address_is_committed() -> None:
    contact = _contact()
    found = [
        f"{path.relative_to(ROOT)}: {address}"
        for path in _files()
        for address in _EMAIL_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))
        if not _allowed(address, contact)
    ]
    assert found == []
