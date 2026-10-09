r"""The LaTeX of abstracts, as plain text (SRCH-19, decision 17).

arXiv abstracts are written in LaTeX: "we propose \textbf{GestureFAR}", "available at
\url{https://github.com/...}", "from $\sim$18--20\% to $\sim$3--6\%". The site shows
them as text, and its search indexed the macros: "textbf" matched the prefix "text".
Text macros give their argument, links their address, citations go, and the symbols of
math give their character ("$\sim$" is "~", "$\pm$" is "±"); a formula left with nothing
but text loses its dollars, and one that still holds markup ("$S^2 \times S^1$") keeps
them. A paper's own macros ("\method", "\ours") stay as written: nothing says what they
stand for. Math is not rendered (no KaTeX).
"""

import re
import unicodedata
from collections.abc import Callable

# Macros whose one argument is their text: "\textbf{GestureFAR}" is "GestureFAR".
_TEXT_MACROS = frozenset({
    "textbf", "textit", "emph", "texttt", "textsc", "textrm", "textsf", "textup", "textmd",
    "textnormal", "underline", "uline", "text", "mbox", "mathrm", "mathbf", "mathit", "mathsf",
    "mathtt", "mathcal", "mathbb", "mathscr", "mathfrak", "boldsymbol", "bm", "operatorname",
})  # fmt: skip
# Macros that say nothing in plain text, with their one argument.
_DROPPED_MACROS = frozenset({"cite", "citep", "citet", "citealp", "ref", "eqref", "label", "color"})
_GREEK = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "eta",
    "theta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "pi",
    "rho",
    "sigma",
    "tau",
    "upsilon",
    "phi",
    "chi",
    "psi",
    "omega",
]
_CAPITAL_GREEK = ["Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi", "Psi", "Omega"]


def _greek(case: str, name: str) -> str:
    # Unicode spells lambda "LAMDA".
    return unicodedata.lookup(f"GREEK {case} LETTER {name.upper().replace('LAMBDA', 'LAMDA')}")


# Switches of size or font, which print nothing: "{\small{https://...}}", "$R_{\rm prod}$".
_SWITCHES = [
    "small",
    "footnotesize",
    "scriptsize",
    "tiny",
    "normalsize",
    "large",
    "Large",
    "LARGE",
    "huge",
    "rm",
    "it",
    "bf",
    "em",
    "sc",
    "tt",
    "sf",
    "sl",
    "bfseries",
    "itshape",
    "ttfamily",
    "sffamily",
    "scshape",
    "upshape",
    "mdseries",
    "normalfont",
]
# Superscripts of text: "km\textsuperscript{2}" is "km²".
_SUPERSCRIPTS = str.maketrans(
    "0123456789+-n",
    "\N{SUPERSCRIPT ZERO}\N{SUPERSCRIPT ONE}\N{SUPERSCRIPT TWO}\N{SUPERSCRIPT THREE}"
    "\N{SUPERSCRIPT FOUR}\N{SUPERSCRIPT FIVE}\N{SUPERSCRIPT SIX}\N{SUPERSCRIPT SEVEN}"
    "\N{SUPERSCRIPT EIGHT}\N{SUPERSCRIPT NINE}\N{SUPERSCRIPT PLUS SIGN}\N{SUPERSCRIPT MINUS}"
    "\N{SUPERSCRIPT LATIN SMALL LETTER N}",
)
# Abbreviations, which keep the space after them: "\etal and".
_ABBREVIATIONS = frozenset({"ie", "eg", "etal", "wrt", "vs", "etc", "LaTeX", "TeX"})
# Macros without argument, and what they print: abbreviations, then math symbols, which take
# the space after them as LaTeX does ("$M^2 \times M^2$").
_WORDS = {
    "ie": "i.e.",
    "eg": "e.g.",
    "etal": "et al.",
    "wrt": "w.r.t.",
    "vs": "vs.",
    "etc": "etc.",
    "LaTeX": "LaTeX",
    "TeX": "TeX",
    "textasciitilde": "~",
    "sim": "~",
    "percent": "%",
    "ldots": "\N{HORIZONTAL ELLIPSIS}",
    "dots": "\N{HORIZONTAL ELLIPSIS}",
    "cdots": "\N{MIDLINE HORIZONTAL ELLIPSIS}",
    "times": "\N{MULTIPLICATION SIGN}",
    "approx": "\N{ALMOST EQUAL TO}",
    "simeq": "\N{ASYMPTOTICALLY EQUAL TO}",
    "pm": "\N{PLUS-MINUS SIGN}",
    "mp": "\N{MINUS-OR-PLUS SIGN}",
    "cdot": "\N{MIDDLE DOT}",
    "infty": "\N{INFINITY}",
    "to": "\N{RIGHTWARDS ARROW}",
    "rightarrow": "\N{RIGHTWARDS ARROW}",
    "leftarrow": "\N{LEFTWARDS ARROW}",
    "Rightarrow": "\N{RIGHTWARDS DOUBLE ARROW}",
    "leftrightarrow": "\N{LEFT RIGHT ARROW}",
    "uparrow": "\N{UPWARDS ARROW}",
    "downarrow": "\N{DOWNWARDS ARROW}",
    "le": "\N{LESS-THAN OR EQUAL TO}",
    "leq": "\N{LESS-THAN OR EQUAL TO}",
    "ge": "\N{GREATER-THAN OR EQUAL TO}",
    "geq": "\N{GREATER-THAN OR EQUAL TO}",
    "ne": "\N{NOT EQUAL TO}",
    "neq": "\N{NOT EQUAL TO}",
    "in": "\N{ELEMENT OF}",
    "notin": "\N{NOT AN ELEMENT OF}",
    "subset": "\N{SUBSET OF}",
    "subseteq": "\N{SUBSET OF OR EQUAL TO}",
    "ll": "\N{MUCH LESS-THAN}",
    "gg": "\N{MUCH GREATER-THAN}",
    "propto": "\N{PROPORTIONAL TO}",
    "ell": "\N{SCRIPT SMALL L}",
    "partial": "\N{PARTIAL DIFFERENTIAL}",
    "nabla": "\N{NABLA}",
    "circ": "\N{RING OPERATOR}",
    "degree": "\N{DEGREE SIGN}",
    "varepsilon": "\N{GREEK SMALL LETTER EPSILON}",
    "vartheta": "\N{GREEK THETA SYMBOL}",
    "varphi": "\N{GREEK SMALL LETTER PHI}",
    **dict.fromkeys(_SWITCHES, ""),
    **{name: _greek("SMALL", name) for name in _GREEK},
    **{name: _greek("CAPITAL", name) for name in _CAPITAL_GREEK},
}
_MACRO_RE = re.compile(r"\\([A-Za-z]+)\*?")
# Escaped characters, and LaTeX's spaces: "\%" is "%", "\," a thin space, "\!" none.
_ESCAPES = {"%": "%", "&": "&", "_": "_", "#": "#", "{": "{", "}": "}", ",": " ", ";": " ", ":": " ", "!": ""}
_ESCAPE_RE = re.compile(r"\\([%&_#{},;:!])")
# An escaped dollar, kept apart while formulas are read.
_DOLLAR = "\ue001"
# Font switches in a group: "{\em e.g.}", "{\it events}". The group stays a group: it may be
# an argument ("B$\acute{\rm e}$zier").
_FONT_GROUP_RE = re.compile(r"\{\\(?:em|it|bf|sc|tt|rm|sl|sf|bfseries|itshape)\s+([^{}]*)\}")
# Accents on a letter, by symbol: "Schr\"odinger", "\'{e}".
_SYMBOL_ACCENT_RE = re.compile(r"""\\(['`^"~])\s*(?:\{(\w)\}|(\w))""")
_ACCENTS = {
    "'": "\N{COMBINING ACUTE ACCENT}",
    "`": "\N{COMBINING GRAVE ACCENT}",
    "^": "\N{COMBINING CIRCUMFLEX ACCENT}",
    '"': "\N{COMBINING DIAERESIS}",
    "~": "\N{COMBINING TILDE}",
}
# Accents on a letter, by name: "\acute{e}", "\hat{y}", "\tilde{O}".
_NAMED_ACCENTS = {
    "acute": "'",
    "grave": "`",
    "hat": "^",
    "ddot": '"',
    "tilde": "~",
}
# A group left outside formulas once macros are read; an unbalanced brace stays.
_GROUP_RE = re.compile(r"(?<!\\)\{([^{}]*)(?<!\\)\}")
# A macro just before a group: the group is its argument ("\method{}", "\href{...}").
_MACRO_END_RE = re.compile(r"\\[A-Za-z]+\*?$")
# A degree: "10$^\circ$", "27^{\circ}C".
_DEGREE_RE = re.compile(r"\^\s*\{?\s*\\circ\s*\}?")
_UNICODE_RE = re.compile(r"\\unicode\{x?([0-9A-Fa-f]{2,6})\}")
_INLINE_MATH_RE = re.compile(r"\\\((.*?)\\\)")
# A formula: what lies between two dollars, but for prices, which `make venues` meets in
# abstracts already plain ("$300,000 ($26,000 vs. $320,000)", 2310.00426): no formula holds
# spaces and is followed by a digit, as a symbol is ("$\sim$18").
_MATH_RE = re.compile(r"\$((?=[^$]*\$(?!\d))[^$]*|[^$\s]*)\$")
# What a formula holds once it is more than text.
_MARKUP_RE = re.compile(r"[\\^_{}]")
# A range between numbers: "18--20"; and a dash: "efficiency---gains".
_RANGE_RE = re.compile(r"(?<=\d)--(?=\d)")
_DASH_RE = re.compile(r"(?<!-)---(?!-)")


def plain_text(text: str) -> str:
    """An abstract's LaTeX as plain text.

    Args:
        text: An abstract, as arXiv gives it.

    Returns:
        The abstract with its text macros, links, citations and math symbols as plain text,
        whitespace collapsed.
    """
    text = text.replace("\\$", _DOLLAR)
    text = _UNICODE_RE.sub(lambda match: chr(int(match[1], 16)), text)
    text = _DEGREE_RE.sub("\N{DEGREE SIGN}", text)
    text = _INLINE_MATH_RE.sub(r"$\1$", text)
    while (grouped := _FONT_GROUP_RE.sub(r"{\1}", text)) != text:
        text = grouped
    text = _SYMBOL_ACCENT_RE.sub(lambda match: _accented(match[2] or match[3], match[1]), text)
    # A formula of text only is text before groups go, or "{8$\times$}" keeps its braces.
    text = _outside_math(_text_formulas(_macros(text)), _ungrouped)
    text = _ESCAPE_RE.sub(lambda match: _ESCAPES[match[1]], text)
    text = _text_formulas(text)
    text = _DASH_RE.sub("\N{EM DASH}", _RANGE_RE.sub("\N{EN DASH}", text))
    return " ".join(text.split()).replace(_DOLLAR, "$")


def _text_formulas(text: str) -> str:
    """The text with each formula that holds no markup as its text, without its dollars."""
    return _MATH_RE.sub(lambda match: match[0] if _MARKUP_RE.search(match[1]) else match[1], text)


def _ungrouped(text: str) -> str:
    """The text without the braces of its groups, but those of a macro left as written."""

    def content(match: re.Match[str]) -> str:
        return match[0] if _MACRO_END_RE.search(text, 0, match.start()) else match[1]

    while (ungrouped := _GROUP_RE.sub(content, text)) != text:
        text = ungrouped
    return text


def _accented(letter: str, accent: str) -> str:
    return unicodedata.normalize("NFC", letter + _ACCENTS[accent])


def _outside_math(text: str, change: Callable[[str], str]) -> str:
    """The text with ``change`` applied to what is outside its formulas."""
    parts = _MATH_RE.split(text)
    # split keeps each formula's content at odd positions.
    return "".join(f"${part}$" if index % 2 else change(part) for index, part in enumerate(parts))


def _macros(text: str) -> str:
    """The text with each macro it knows replaced, innermost arguments included."""
    parts: list[str] = []
    position = 0
    while match := _MACRO_RE.search(text, position):
        parts.append(text[position : match.start()])
        replaced, position = _replaced(match[1], text, match.end())
        if match[1] in _DROPPED_MACROS and replaced == "":
            # "RaTEScore~\cite{x} decrease": the citation's space goes with it.
            parts[-1] = parts[-1].rstrip(" ~")
        parts.append(match[0] if replaced is None else replaced)
    parts.append(text[position:])
    return "".join(parts)


def _replaced(name: str, text: str, start: int) -> tuple[str | None, int]:
    """What the macro ``name``, whose arguments start at ``start``, prints, and where it ends.

    ``None`` for a macro it does not know, or whose arguments are missing.
    """
    if name in _WORDS:
        if name not in _ABBREVIATIONS:
            while start < len(text) and text[start] == " ":
                start += 1
        return _WORDS[name], start
    if name in {"href", "textcolor"}:
        return _two_arguments(name, text, start)
    argument, end = _argument(text, start)
    if argument is None or (name not in _TEXT_MACROS and name not in _ONE_ARGUMENT):
        return None, start
    inner = _macros(argument)
    if name in _TEXT_MACROS:
        return inner, end
    return _ONE_ARGUMENT[name](argument, inner), end


def _two_arguments(name: str, text: str, start: int) -> tuple[str | None, int]:
    r"""What ``\href{target}{shown}`` or ``\textcolor{color}{shown}`` prints, and where it ends."""
    target, end = _argument(text, start)
    if target is None:
        return None, start
    shown, after = _argument(text, end)
    if shown is None:
        # "Homepage: \href{https://...}", its text forgotten: the address is shown.
        return (target, end) if name == "href" else (None, start)
    return _link(target, _macros(shown)) if name == "href" else _macros(shown), after


def _link(target: str, shown: str) -> str:
    """A link as text: what it shows, and where it leads when that is not shown."""
    if not shown or shown == target:
        return target
    return shown if shown.startswith(("http", "www.")) else f"{shown} ({target})"


# Macros of one argument that print something else than it: (the argument, as written
# and with its own macros replaced) -> text.
_ONE_ARGUMENT = {
    **dict.fromkeys(_DROPPED_MACROS, lambda _argument, _inner: ""),
    "url": lambda argument, _inner: argument,
    "textsuperscript": lambda _argument, inner: inner.translate(_SUPERSCRIPTS),
    "footnote": lambda _argument, inner: f" ({inner})",
    **{
        name: lambda _argument, inner, accent=accent: _accented(inner, accent) if len(inner) == 1 else inner
        for name, accent in _NAMED_ACCENTS.items()
    },
    "sqrt": lambda _argument, inner: (
        f"\N{SQUARE ROOT}{inner}" if len(inner) == 1 else f"\N{SQUARE ROOT}({inner})"
    ),
}


def _argument(text: str, start: int) -> tuple[str | None, int]:
    """The braced argument at ``start`` (after spaces and an optional ``[...]``), and where it ends."""
    position = start
    while position < len(text) and text[position] == " ":
        position += 1
    if position < len(text) and text[position] == "[":
        close = text.find("]", position)
        if close == -1:
            return None, start
        position = close + 1
    if position >= len(text) or text[position] != "{":
        return None, start
    depth = 0
    for index in range(position, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[position + 1 : index], index + 1
    return None, start
