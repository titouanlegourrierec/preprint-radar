"""Exception hierarchy for the package."""


class PreprintRadarError(Exception):
    """Base class for all errors raised by ``preprint_radar``."""


class FetchError(PreprintRadarError):
    """Raised when a resource cannot be retrieved.

    Attributes:
        status: The HTTP status the server answered with, ``None`` if it did not answer.
        retry_after: The seconds its ``Retry-After`` header asked to wait, if it sent one.
    """

    def __init__(self, message: str, *, status: int | None = None, retry_after: float | None = None) -> None:
        """Create the error, with the HTTP status of the refusal and its wait, if any."""
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class NotFoundError(FetchError):
    """Raised when a resource does not exist (HTTP 404)."""


class ConfigurationError(PreprintRadarError):
    """A setting the command needs is missing (a token)."""


class ParseError(PreprintRadarError):
    """Raised when a document does not have the expected structure."""


class StoreError(PreprintRadarError):
    """Raised when the on-disk paper store is invalid."""


class SchemaVersionError(StoreError):
    """Raised when a file of the store was written with another ``schema_version``."""
