"""Terminal output: colors and tables in a terminal, plain text elsewhere.

In CI, pipes and tests the output stays the plain text it always was (one line per log
record, no wrapping), so that logs remain easy to read back and to grep. In GitHub Actions,
commands also write to the run's page: its job summary and annotations.
"""

import logging
import os
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler

# Messages are plain text: square brackets and ":name:" are not markup or emoji codes.
console = Console(markup=False, emoji=False, soft_wrap=True)
err_console = Console(stderr=True, markup=False, emoji=False, soft_wrap=True)

PLAIN_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
PLAIN_TIME_FORMAT = "%H:%M:%S"


def configure_logging(level: int) -> None:
    """Log at ``level`` to stderr: through rich in a terminal, as plain lines otherwise."""
    handler = log_handler()
    logging.basicConfig(level=level, handlers=[handler])


def log_handler() -> logging.Handler:
    """A rich handler in a terminal (level and time in columns), else plain log lines."""
    if err_console.is_terminal:
        handler: logging.Handler = RichHandler(
            console=err_console, show_path=False, markup=False, log_time_format="[%X]"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(PLAIN_LOG_FORMAT, PLAIN_TIME_FORMAT))
    return handler


def github_summary(markdown: str) -> None:
    """Append Markdown to the job summary of a GitHub Actions run; nothing elsewhere."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as summary:
            summary.write(markdown.rstrip("\n") + "\n\n")


def github_annotation(level: Literal["notice", "warning", "error"], title: str, message: str) -> None:
    """Show a message at the top of a GitHub Actions run's page; nothing elsewhere."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # Workflow commands end at a newline, and use % for escapes.
        escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        console.print(f"::{level} title={title}::{escaped}")
