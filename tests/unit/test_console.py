import logging
import re
from pathlib import Path

import pytest
from rich.console import Console
from rich.logging import RichHandler

from preprint_radar.console import PLAIN_LOG_FORMAT, github_annotation, github_summary, log_handler


def test_logs_are_plain_lines_outside_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("preprint_radar.console.err_console", Console(force_terminal=False))

    handler = log_handler()

    assert type(handler) is logging.StreamHandler
    assert handler.formatter is not None
    assert handler.formatter._fmt == PLAIN_LOG_FORMAT  # noqa: SLF001 - the format is the contract
    record = logging.LogRecord("preprint_radar.collect", logging.INFO, "", 0, "Hello", None, None)
    assert re.fullmatch(r"\d\d:\d\d:\d\d INFO preprint_radar.collect: Hello", handler.format(record))


def test_logs_go_through_rich_in_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("preprint_radar.console.err_console", Console(force_terminal=True))

    assert isinstance(log_handler(), RichHandler)


def test_the_job_summary_is_written_in_github_actions_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    github_summary("**Papers.** nothing")
    assert not summary.exists()

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    github_summary("**Papers.** 3 new\n")
    github_summary("### Data")

    assert summary.read_text(encoding="utf-8") == "**Papers.** 3 new\n\n### Data\n\n"


def test_annotations_are_printed_in_github_actions_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    github_annotation("warning", "Stale data", "elsewhere")
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    github_annotation("error", "Archive not updated", "50% of the counts\nand more")

    assert capsys.readouterr().out == "::error title=Archive not updated::50%25 of the counts%0Aand more\n"
