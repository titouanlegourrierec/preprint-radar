"""Exception hierarchy for the package."""


class PreprintRadarError(Exception):
    """Base class for all errors raised by ``preprint_radar``."""


class FetchError(PreprintRadarError):
    """Raised when a resource cannot be retrieved."""


class NotFoundError(FetchError):
    """Raised when a resource does not exist (HTTP 404)."""


class ParseError(PreprintRadarError):
    """Raised when a document does not have the expected structure."""


class StoreError(PreprintRadarError):
    """Raised when the on-disk paper store is invalid."""
