"""Helpers over LaTeXML's markup: the text of a node, its markers, without its notes."""

from bs4 import BeautifulSoup, NavigableString, Tag


def _pruned(node: Tag) -> Tag:
    """A copy of the node without contact labels, e-mails, links and note decorations.

    The copied node itself is kept even when it is a note: only what it contains is noise.
    """
    copy = BeautifulSoup(str(node), "html.parser")
    root = next(iter(copy.find_all(name=True, limit=1)), None)
    for noise in copy.select(
        ".ltx_contact_name, .ltx_role_email, .ltx_note, .ltx_note_mark, .ltx_note_type, a"
    ):
        if noise is not root:
            noise.decompose()
    return copy


def _marked_text(node: Tag, *, without_notes: bool = False) -> str:
    """Node text with each superscript as a ``⟨marker⟩`` token, but footnote marks with ``without_notes``."""
    copy = BeautifulSoup(str(node), "html.parser")
    for note in copy.select(".ltx_role_footnotemark") if without_notes else ():
        note.decompose()
    for sup in copy.select("sup"):
        sup.replace_with(sup.get_text() if _inside_word(sup) else f"⟨{' '.join(sup.get_text().split())}⟩")
    return " ".join(copy.get_text().split())


def _inside_word(sup: Tag) -> bool:
    """Whether a superscript is part of a word ("Hyper<sup>2</sup>labs") rather than a marker.

    Between two lowercase letters only: a marker between words ("University<sup>1</sup>Nokia")
    still separates them.
    """
    before, after = sup.previous_sibling, sup.next_sibling
    return (
        isinstance(before, NavigableString)
        and before[-1:].islower()
        and isinstance(after, NavigableString)
        and after[:1].islower()
    )


def _plain_text(node: Tag) -> str:
    """Node text without superscripts, whitespace collapsed."""
    copy = BeautifulSoup(str(node), "html.parser")
    for sup in copy.select("sup"):
        sup.decompose()
    return " ".join(copy.get_text().split())
