"""A paper's code: the repository or Hugging Face page its abstract or comments link (PROD-18).

The site finds it the same way (``web/src/code.ts`` and ``linkify.ts``, PROD-12): the first
repository on GitHub or GitLab, else models, data or a demo on the Hugging Face Hub. Both
read ``tests/fixtures/code-cases.json``, so that the stars a card shows are those of the
link it shows. On top of the link, the pipeline names what to ask the services for: a
GitHub repository as ``owner/name``, a Hub page as ``models/owner/name`` (or ``datasets/``,
``spaces/``), and whether the link points into a folder of a larger repository.
"""

import re
from dataclasses import dataclass
from typing import Literal

# `linkify.ts`: a URL, and the punctuation that usually ends the sentence rather than it.
_URL_RE = re.compile(r"https?://[^\s<>\"'`]+")
_TRAILING_PUNCTUATION_RE = re.compile(r"[.,;:!?]+$")
# `code.ts`: a repository, an owner and a name on a code host; a user's page or a project
# page (`*.github.io`) is not one. Models, data or a demo on the Hub, not its page of the
# paper (`papers/2610.01234`).
_REPOSITORY_RE = re.compile(r"^https?://(?:www\.)?(?:github\.com|gitlab\.com)/[^/?#]+/[^/?#]+", re.IGNORECASE)
_HUB_RE = re.compile(r"^https?://(?:www\.)?huggingface\.co/(?!papers/)[^/?#]+/[^/?#]+", re.IGNORECASE)
# The names GitHub and the Hub allow: what follows is a typo of the paper's
# ("GroundAnything](https://...", a Markdown link written in plain text).
_GITHUB_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[a-z0-9-]+)/(?P<name>[a-z0-9._-]+)(?P<rest>[^?#]*)",
    re.IGNORECASE,
)
_HUB_PAGE_RE = re.compile(
    r"^https?://(?:www\.)?huggingface\.co/(?:(?P<kind>datasets|spaces)/)?"
    r"(?P<owner>[a-z0-9._-]+)/(?P<name>[a-z0-9._-]+)",
    re.IGNORECASE,
)
# First segments of Hub addresses that are not a model's owner.
_HUB_SECTIONS = frozenset({"blog", "collections", "docs", "learn", "organizations", "tasks"})


@dataclass(frozen=True, slots=True)
class CodeLink:
    """A paper's code, as its card links it.

    Attributes:
        url: The link, as the paper writes it.
        host: Where it is.
        key: What to ask the host for: ``owner/name`` on GitHub, lowercase;
            ``models/owner/name`` (or ``datasets/``, ``spaces/``) on the Hub; ``None`` on
            GitLab, or for a Hub page that is no model, dataset or demo.
        folder: The link points into a folder of the repository
            (``.../tree/main/projects/pnp-vqa``): its stars are the whole repository's.
    """

    url: str
    host: Literal["github", "gitlab", "huggingface"]
    key: str | None
    folder: bool = False


def urls(text: str) -> list[str]:
    """The URLs of a text, as the site links them (``linkify.ts``)."""
    found: list[str] = []
    for match in _URL_RE.finditer(text):
        url = _trimmed(match[0])
        if re.sub(r"^https?://", "", url):
            found.append(url)
    return found


def _trimmed(candidate: str) -> str:
    """The URL without the punctuation that ends its sentence, nor an unopened bracket."""
    url = _TRAILING_PUNCTUATION_RE.sub("", candidate)
    while url.endswith((")", "]")):
        close = url[-1]
        if url.count("(" if close == ")" else "[") >= url.count(close):
            break
        url = _TRAILING_PUNCTUATION_RE.sub("", url[:-1])
    return url


def code_url(abstract: str | None, comments: str | None) -> str | None:
    """The paper's code (``codeUrl`` of ``code.ts``): its first repository, else its Hub page.

    Args:
        abstract: The paper's abstract, ``None`` when not retrieved.
        comments: Its authors' comments, ``None`` when there are none.
    """
    links = [url for text in (abstract, comments) if text for url in urls(text)]
    return next((url for url in links if _REPOSITORY_RE.match(url)), None) or next(
        (url for url in links if _HUB_RE.match(url)), None
    )


def code_link(abstract: str | None, comments: str | None) -> CodeLink | None:
    """The paper's code, with what to ask its host for; ``None`` when it links none.

    Args:
        abstract: The paper's abstract, ``None`` when not retrieved.
        comments: Its authors' comments, ``None`` when there are none.
    """
    url = code_url(abstract, comments)
    if url is None:
        return None
    host = url.split("/", 3)[2].lower().removeprefix("www.")
    if host == "gitlab.com":
        return CodeLink(url, "gitlab", None)
    if host == "github.com":
        github = _GITHUB_RE.match(url)
        name = github["name"].removesuffix(".git") if github else ""
        if github is None or not name.strip("."):
            return CodeLink(url, "github", None)
        return CodeLink(
            url, "github", f"{github['owner']}/{name}".lower(), folder=_into_folder(github["rest"])
        )
    hub = _HUB_PAGE_RE.match(url)
    if hub is None or (hub["kind"] is None and hub["owner"].lower() in _HUB_SECTIONS):
        return CodeLink(url, "huggingface", None)
    return CodeLink(url, "huggingface", f"{hub['kind'] or 'models'}/{hub['owner']}/{hub['name']}")


def _into_folder(rest: str) -> bool:
    """Whether the path after ``owner/name`` leads into a folder, past a branch or a root file.

    ``/tree/main`` is the repository; ``/blob/main/train.py``, a file at its root, too;
    ``/tree/main/projects/x`` and ``/blob/main/configs/x/README.md`` are a folder of it.
    """
    segments = [segment for segment in rest.split("/") if segment]
    if not segments or segments[0] not in {"tree", "blob"}:
        return False
    inside = segments[2:]  # after the kind and the branch
    return bool(inside) if segments[0] == "tree" else len(inside) > 1
