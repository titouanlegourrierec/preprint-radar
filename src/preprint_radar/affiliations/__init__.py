"""The affiliations of arXiv HTML pages (LaTeXML output): what each paper's authors are at.

``sources/arxiv_html.py`` reads the page and calls these, in turn: the page's sources of
affiliations (``sources``), joined from their lines (``lines``) and cleaned
(``cleaning``), then who is where (``mapping``), over the shared words and patterns
(``vocabulary``), name folding (``folding``) and markup helpers (``dom``). Split from one
module of 2,400 lines along its call graph (EXT-6).
"""
