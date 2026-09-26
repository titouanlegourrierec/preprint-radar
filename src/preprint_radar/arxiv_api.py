"""Client for the arXiv Atom API (https://info.arxiv.org/help/api/)."""

import logging
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import batched
from urllib.parse import urlencode
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.paper_page import clean_affiliation

logger = logging.getLogger(__name__)

API_URL = "https://export.arxiv.org/api/query"
MAX_IDS_PER_REQUEST = 100

_NAMESPACES = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
# "http://arxiv.org/abs/2609.30245v1" -> "2609.30245"; also handles "hep-th/9901001v2".
_ENTRY_ID_RE = re.compile(r"/abs/(?P<id>.+?)(?:v\d+)?$")


@dataclass(frozen=True, slots=True)
class ApiMetadata:
    """Metadata returned by the API that the listing pages do not provide.

    Attributes:
        arxiv_id: arXiv identifier without version.
        abstract: Abstract, whitespace-normalized.
        affiliations: Distinct affiliations declared by the submitter (often empty).
    """

    arxiv_id: str
    abstract: str
    affiliations: tuple[str, ...]


def fetch_metadata(
    client: HttpClient, arxiv_ids: Sequence[str], *, batch_size: int = MAX_IDS_PER_REQUEST
) -> dict[str, ApiMetadata]:
    """Fetch API metadata for many papers, batching identifiers.

    Args:
        client: HTTP client, ideally rate-limited to one call every 3 seconds.
        arxiv_ids: Identifiers to look up.
        batch_size: Number of identifiers per request.

    Returns:
        Metadata keyed by arXiv identifier. Unknown identifiers are absent. On the first
        failed batch, requests stop and the metadata gathered so far is returned.
    """
    results: dict[str, ApiMetadata] = {}
    for batch in batched(arxiv_ids, batch_size, strict=False):
        logger.info("Fetching API metadata for %d papers", len(batch))
        # The API front end rejects percent-encoded commas (406), so keep them literal.
        query = urlencode({"id_list": ",".join(batch), "max_results": len(batch), "start": 0}, safe=",/")
        try:
            feed = client.get_text(f"{API_URL}?{query}")
            results.update((meta.arxiv_id, meta) for meta in parse_feed(feed))
        except (FetchError, ParseError) as exc:
            # The API throttles by client: insisting only prolongs the block.
            logger.warning("Stopping API requests for this run: %s", exc)
            break
    return results


def parse_feed(xml: str) -> Iterator[ApiMetadata]:
    """Parse an Atom feed returned by the arXiv API.

    Args:
        xml: Raw XML of the feed.

    Yields:
        Metadata of each entry.

    Raises:
        ParseError: If the document is not valid XML.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        msg = f"Invalid arXiv API response: {exc}"
        raise ParseError(msg) from exc

    for entry in root.iterfind("atom:entry", _NAMESPACES):
        entry_id = _text(entry, "atom:id")
        match = _ENTRY_ID_RE.search(entry_id)
        if match is None:
            # The API reports errors (e.g. a malformed id) as entries without an /abs/ URL.
            logger.warning("Skipping API entry %r: %s", entry_id, _text(entry, "atom:summary"))
            continue
        yield _parse_entry(entry, match.group("id"))


def _parse_entry(entry: Element, arxiv_id: str) -> ApiMetadata:
    affiliations: dict[str, None] = {}  # ordered set
    for node in entry.iterfind("atom:author/arxiv:affiliation", _NAMESPACES):
        # Submitters sometimes type notes here ("Corresponding author is ..."): filter them.
        if name := clean_affiliation(node.text or ""):
            affiliations.setdefault(name)

    return ApiMetadata(
        arxiv_id=arxiv_id,
        abstract=_normalize(_text(entry, "atom:summary")),
        affiliations=tuple(affiliations),
    )


def _text(element: Element, path: str) -> str:
    node = element.find(path, _NAMESPACES)
    return node.text or "" if node is not None else ""


def _normalize(text: str) -> str:
    return " ".join(text.split())
