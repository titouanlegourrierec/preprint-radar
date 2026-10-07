"""Read abstracts from the arXiv RSS feeds (https://info.arxiv.org/help/rss.html).

A category feed lists everything announced in the latest mailing (new submissions,
cross-lists and replacements) with abstracts, in a single request. It is the cheapest
way to get the abstracts of the day.
"""

import logging
import re
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.latex import plain_text

logger = logging.getLogger(__name__)

RSS_URL = "https://rss.arxiv.org/rss/{category}"

_ABS_LINK_RE = re.compile(r"/abs/(?P<id>.+?)(?:v\d+)?$")
_ABSTRACT_RE = re.compile(r"Abstract:\s*(?P<abstract>.+)", re.DOTALL)


def fetch_rss_abstracts(client: HttpClient, category: str) -> dict[str, str]:
    """Fetch the abstracts of the latest announcement of a category.

    Args:
        client: HTTP client.
        category: arXiv category, e.g. ``"cs.CV"``.

    Returns:
        Abstracts keyed by arXiv identifier.

    Raises:
        FetchError: If the feed cannot be retrieved.
        ParseError: If the feed is not valid XML.
    """
    logger.info("Fetching the RSS feed of %s", category)
    return parse_rss_abstracts(client.get_text(RSS_URL.format(category=category)))


def parse_rss_abstracts(xml: str) -> dict[str, str]:
    """Extract abstracts from an arXiv RSS feed.

    Args:
        xml: Raw XML of the feed.

    Returns:
        Abstracts keyed by arXiv identifier, whitespace-normalized.

    Raises:
        ParseError: If the feed is not valid XML.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        msg = f"Invalid arXiv RSS feed: {exc}"
        raise ParseError(msg) from exc

    abstracts: dict[str, str] = {}
    for item in root.iterfind("channel/item"):
        if parsed := _parse_item(item):
            arxiv_id, abstract = parsed
            abstracts[arxiv_id] = abstract
    return abstracts


def _parse_item(item: Element) -> tuple[str, str] | None:
    link = _ABS_LINK_RE.search(item.findtext("link", default=""))
    abstract = _ABSTRACT_RE.search(item.findtext("description", default=""))
    if link is None or abstract is None:
        logger.debug("Skipping unexpected RSS item: %s", item.findtext("title"))
        return None
    return link.group("id"), plain_text(abstract.group("abstract"))
