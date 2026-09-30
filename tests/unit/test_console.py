import logging

import pytest
from rich.console import Console
from rich.logging import RichHandler

from preprint_radar.console import PLAIN_LOG_FORMAT, log_handler


def test_logs_are_plain_lines_outside_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("preprint_radar.console.err_console", Console(force_terminal=False))

    handler = log_handler()

    assert type(handler) is logging.StreamHandler
    assert handler.formatter is not None
    assert handler.formatter._fmt == PLAIN_LOG_FORMAT  # noqa: SLF001 - the format is the contract


def test_logs_go_through_rich_in_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("preprint_radar.console.err_console", Console(force_terminal=True))

    assert isinstance(log_handler(), RichHandler)
