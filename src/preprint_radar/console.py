"""Terminal output: colors and tables in a terminal, plain text elsewhere.

In CI, pipes and tests the output stays the plain text it always was (one line per log
record, no wrapping), so that logs remain easy to read back and to grep.
"""

import logging

from rich.console import Console
from rich.logging import RichHandler

# Messages are plain text: square brackets and ":name:" are not markup or emoji codes.
console = Console(markup=False, emoji=False, soft_wrap=True)
err_console = Console(stderr=True, markup=False, emoji=False, soft_wrap=True)

PLAIN_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


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
        handler.setFormatter(logging.Formatter(PLAIN_LOG_FORMAT))
    return handler
