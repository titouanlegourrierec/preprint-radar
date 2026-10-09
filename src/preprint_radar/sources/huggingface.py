"""The likes of the models, datasets and demos papers link on the Hugging Face Hub (PROD-18).

About one paper in 400 links the Hub rather than a repository (65 of 27,000 in October
2026): one request each, without a key, to ``/api/models/<id>`` (or ``datasets``,
``spaces``), whose ``likes`` the site shows as GitHub's stars, but apart from them.
"""

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from preprint_radar.console import Advance, no_progress
from preprint_radar.exceptions import FetchError, NotFoundError
from preprint_radar.http import HttpClient

logger = logging.getLogger(__name__)

HUGGINGFACE_API_URL = "https://huggingface.co/api"
# The Hub limits anonymous requests per five minutes; stay well below.
HUGGINGFACE_DELAY_SECONDS = 0.5
# The Hub answers 401 for a repository that does not exist, as for a private one.
_UNKNOWN = frozenset({401})


@dataclass(frozen=True, slots=True)
class Likes:
    """What the Hub said of the pages asked for.

    Attributes:
        likes: The likes of each page it knows, by ``models/owner/name`` (or ``datasets/``,
            ``spaces/``).
        missing: Those it does not know (deleted, private or gated). The others failed:
            asked again next time.
    """

    likes: dict[str, int] = field(default_factory=dict)
    missing: set[str] = field(default_factory=set)


def fetch_likes(client: HttpClient, pages: Iterable[str], *, progress: Advance = no_progress) -> Likes:
    """The likes of Hub pages, one request each.

    Args:
        client: HTTP client for the Hub.
        pages: ``models/owner/name``, ``datasets/owner/name`` or ``spaces/owner/name``.
        progress: Told of each page asked for.

    Returns:
        Their likes, and those the Hub does not know.
    """
    found = Likes()
    wanted = sorted(set(pages))
    for page in wanted:
        try:
            payload = json.loads(client.get_text(f"{HUGGINGFACE_API_URL}/{page}"))
            found.likes[page] = int(payload["likes"])
        except NotFoundError:
            found.missing.add(page)
        except FetchError as exc:
            if exc.status in _UNKNOWN:
                found.missing.add(page)
            else:
                logger.warning("Hugging Face lookup of %s failed: %s", page, exc)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Unexpected Hugging Face answer for %s: %s", page, exc)
        finally:
            progress(1)
    logger.info(
        "The Hub knows %d of %d pages (%d not found)", len(found.likes), len(wanted), len(found.missing)
    )
    return found
