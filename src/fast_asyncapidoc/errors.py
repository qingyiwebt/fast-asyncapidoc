"""Public exceptions raised by :mod:`fast_asyncapidoc`."""


class AsyncAPIDocError(Exception):
    """Base exception for fast-asyncapidoc errors."""


class InvalidAsyncAPIDecoratorError(AsyncAPIDocError, ValueError):
    """Raised when an ``@asyncapi`` declaration is invalid."""


class DuplicateOperationIdError(AsyncAPIDocError, ValueError):
    """Raised when two operations use the same explicit operation ID."""


class MissingYamlDependencyError(AsyncAPIDocError, RuntimeError):
    """Raised when YAML serialization is requested without PyYAML installed."""
