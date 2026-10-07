import pytest
from tests.conftest import OfflineError

from preprint_radar.http import HttpClient


def test_a_test_cannot_reach_the_network() -> None:
    client = HttpClient(min_interval=0)

    with pytest.raises(OfflineError, match=r"asked for https://arxiv\.org/list/cs\.CV/recent"):
        client.get_text("https://arxiv.org/list/cs.CV/recent")
