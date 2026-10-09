import json
from typing import Any

import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.code import CodeLink, code_link, code_url, urls

# The links the site's `codeUrl` finds too (web/tests/code.test.ts reads the same cases).
CASES: list[dict[str, Any]] = json.loads((FIXTURES_DIR / "code-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[str(index) for index in range(len(CASES))])
def test_the_code_link_is_the_sites(case: dict[str, Any]) -> None:
    assert code_url(case["abstract"], case.get("comments")) == case["url"]
    link = code_link(case["abstract"], case.get("comments"))
    assert (link.url if link else None) == case["url"]
    if link is not None and "key" in case:
        assert link.key == case["key"]
    if link is not None and "folder" in case:
        assert link.folder is case["folder"]


def test_hosts() -> None:
    assert code_link("https://gitlab.com/a/b", None) == CodeLink("https://gitlab.com/a/b", "gitlab", None)
    assert code_link("https://github.com/a/.git", None) == CodeLink(
        "https://github.com/a/.git", "github", None
    )
    assert code_link("https://github.com/a_b/c", None) == CodeLink("https://github.com/a_b/c", "github", None)
    hub = code_link("https://huggingface.co/spaces/a/demo", None)
    assert hub == CodeLink("https://huggingface.co/spaces/a/demo", "huggingface", "spaces/a/demo")
    assert code_link(None, None) is None


def test_urls_keep_brackets_they_open() -> None:
    assert urls("(see https://x.io/a_(b)).") == ["https://x.io/a_(b)"]
    assert urls("[https://x.io/a]") == ["https://x.io/a"]
    assert urls("http:// and https://.") == []
