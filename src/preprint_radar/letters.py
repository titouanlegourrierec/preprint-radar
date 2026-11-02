"""Letters written plainly wherever names are compared (AFF-24, EXT-7).

Those that do not decompose into a base letter and an accent: "Bartłomiej" and
"Bartlomiej", "Søren" and "Soren" are one name for the extraction (``arxiv_html.name_key``),
the institutions' keys (``institutions.search_key``), the placement of other services'
authors (``names.same_person``) and the site (``fold`` in ``web/src/text.ts``).
"""

PLAIN_LETTERS = str.maketrans({
    "\N{LATIN SMALL LETTER DOTLESS I}": "i",
    "\N{LATIN SMALL LETTER L WITH STROKE}": "l",
    "\N{LATIN SMALL LETTER O WITH STROKE}": "o",
    "\N{LATIN SMALL LETTER D WITH STROKE}": "d",
    "\N{LATIN SMALL LETTER SHARP S}": "ss",
    "\N{LATIN SMALL LETTER AE}": "ae",
})  # fmt: skip
