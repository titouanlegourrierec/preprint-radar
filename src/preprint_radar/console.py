"""Terminal output: colors and tables in a terminal, plain text elsewhere.

In CI, pipes and tests the output stays the plain text it always was (one line per log
record, no wrapping), so that logs remain easy to read back and to grep. In GitHub Actions,
commands also write to the run's page: its job summary and annotations. The long steps
draw a progress bar in a terminal (:func:`progress`), and only there.
"""

import logging
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

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


type Advance = Callable[[int], object]
"""What a long step calls with the number of items it has just done (:func:`progress`)."""


def no_progress(_done: int) -> None:
    """An :data:`Advance` that shows nothing: the default of the steps that take one."""


@contextmanager
def progress(description: str, total: int) -> Generator[Advance]:
    """A progress bar on stderr for a step of ``total`` items, in a terminal only.

    The bar counts the items done, the time spent and the time left; log records print
    above it. In CI, pipes and tests there is none, whose redrawing would be noise among
    the log lines: the steps log their own progress there.

    Args:
        description: What the step does ("GitHub stars").
        total: How many items it will do.

    Yields:
        The function to call with the number of items done since its last call.
    """
    if not err_console.is_terminal or total <= 0:
        yield no_progress
        return
    columns = (
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("left"),
        TimeRemainingColumn(),
    )
    with Progress(*columns, console=err_console) as bar:
        task = bar.add_task(description, total=total)
        yield lambda done: bar.advance(task, done)


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
