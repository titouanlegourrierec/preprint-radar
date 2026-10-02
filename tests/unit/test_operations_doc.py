"""``docs/operations.md`` quotes what the code prints: each quoted signal must still exist."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
RUNBOOK = ROOT / "docs" / "operations.md"
# A signal paragraph: from "**Signal.**" to the next blank line.
_SIGNAL_RE = re.compile(r"\*\*Signal\.\*\*(.*?)(?:\n\n|\Z)", re.DOTALL)
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")


def _code() -> str:
    """Everything that prints a signal: the package, the workflows and their scripts."""
    paths = [
        *(ROOT / "src").rglob("*.py"),
        *(ROOT / ".github").rglob("*.yml"),
        *(ROOT / ".github").rglob("*.sh"),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _signals() -> list[str]:
    text = RUNBOOK.read_text(encoding="utf-8")
    return [
        " ".join(span.split())
        for paragraph in _SIGNAL_RE.findall(text)
        for span in _CODE_SPAN_RE.findall(paragraph)
    ]


def test_every_symptom_quotes_a_signal() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    sections = re.split(r"^#{2,3} ", text, flags=re.MULTILINE)[1:]
    with_signal = [section for section in sections if "**Signal.**" in section]
    assert len(with_signal) >= 10
    assert len(_signals()) >= 20


def test_quoted_signals_are_printed_by_the_code() -> None:
    code = " ".join(_code().split())
    missing = [signal for signal in _signals() if signal not in code]
    assert missing == []
