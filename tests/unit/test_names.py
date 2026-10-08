import pytest

from preprint_radar.names import name_words, same_person


@pytest.mark.parametrize(
    ("listed", "named"),
    [
        ("Mahdi Hosseini", "Mahdi S. Hosseini"),  # a middle initial
        ("Alexey Dosovitskiy", "Dosovitskiy, Alexey"),  # surname first
        ("Mahdi Hosseini", "M. Hosseini"),  # initials
        ("Jin-Chao Wang", "Jinchao Wang"),  # a hyphenated given name
        ("Søren Hauberg", "Soren Hauberg"),  # folded letters
        ("Tomás Lozano-Pérez", "Tomas Lozano-Perez"),  # accents
    ],
)
def test_same_person(listed: str, named: str) -> None:
    assert same_person(listed, named)
    assert same_person(named, listed)


@pytest.mark.parametrize(
    ("listed", "named"),
    [
        ("Thomas Plötz", "Thomas Ploetz"),  # a transliteration is another spelling
        ("Mahdi Hosseini", "Ali Hosseini"),
        ("Mahdi Hosseini", "Mahdi Rezaei"),
        ("Mahdi Hosseini", ""),
        ("", "Mahdi Hosseini"),
    ],
)
def test_other_people(listed: str, named: str) -> None:
    assert not same_person(listed, named)


def test_name_words() -> None:
    assert name_words("Jean-Pierre D'Arcy") == ["jeanpierre", "darcy"]
    assert name_words("Y. LeCun") == ["y", "lecun"]
