"""Exception hierarchy for the package."""


class PreprintRadarError(Exception):
    """Base class for all errors raised by ``preprint_radar``."""


class FetchError(PreprintRadarError):
    """Raised when a resource cannot be retrieved.

    Attributes:
        status: The HTTP status the server answered with, ``None`` if it did not answer.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        """Create the error, with the HTTP status of the refusal if there was one."""
        super().__init__(message)
        self.status = status


class NotFoundError(FetchError):
    """Raised when a resource does not exist (HTTP 404)."""


class ParseError(PreprintRadarError):
    """Raised when a document does not have the expected structure."""


class StoreError(PreprintRadarError):
    """Raised when the on-disk paper store is invalid."""
