import pytest

from preprint_radar.withdrawal import is_withdrawn


@pytest.mark.parametrize(
    "comments",
    [
        "This paper has been withdrawn by the author due to a sign error in equation 1",
        "Withdrawn by the authors: the work is still being finalized",
        "We would like to withdraw this paper for further revision",
        "The authors request withdrawal because the manuscript needs substantial revision",
        "arXiv admin note: this submission has been withdrawn by arXiv administrators",
        "I want to withdraw it from arXiv to revise it further",
        "Duplicate submission, thus withdraw one of the versions",
        "Temporarily withdrawn for institutional review",
    ],
)
def test_the_comments_of_a_withdrawn_paper(comments: str) -> None:
    assert is_withdrawn(comments)


@pytest.mark.parametrize(
    "comments",
    [
        None,
        "Accepted to CVPR 2026",
        "This paper has been withdrawn from the XYZ workshop at ECCV 2018",
        "Accepted to a workshop. Withdrawn from the proceedings because the author could not attend",
        "Desk-rejected after a withdrawal from ICLR",
        "V1 has been withdrawn due to a template issue; please refer to v2",
        "The wrong submission has now been withdrawn, and we replace the old one here",
        "A revised version of the withdrawn paper, with new experiments",
    ],
)
def test_comments_that_mention_another_withdrawal(comments: str | None) -> None:
    assert not is_withdrawn(comments)
