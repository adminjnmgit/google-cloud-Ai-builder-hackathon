"""Domain exceptions. The API layer maps these to HTTP status codes; the CLI prints them."""


class OrbitError(Exception):
    """Base class for errors the application raises on purpose."""


class ClientError(OrbitError):
    """The caller sent something unusable. ``status`` is the HTTP status the API answers with."""

    status = 400


class NotFoundError(ClientError):
    status = 404


class ConfigError(OrbitError):
    """An environment variable has a value the application cannot use."""


class PipelineBusy(OrbitError):
    """Another pipeline run is already in progress in this process."""


class SourceError(OrbitError, ValueError):
    """The report source is missing, unreadable or malformed."""


class NoEventsProduced(OrbitError, ValueError):
    """A run found no events. It fails rather than replace good data with nothing."""


class DatabaseNotReady(OrbitError):
    """MySQL is unreachable, or its schema is not at the latest migration."""
