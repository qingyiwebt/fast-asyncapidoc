"""Public exceptions raised by :mod:`fast_asyncapidoc`."""


class AsyncAPIDocError(Exception):
    """Base exception for fast-asyncapidoc errors."""


class InvalidAsyncAPIDecoratorError(AsyncAPIDocError, ValueError):
    """Raised when an ``@asyncapi_operation`` declaration is invalid."""


class InvalidAsyncAPIChannelError(AsyncAPIDocError, ValueError):
    """Raised when an ``@asyncapi_channel`` declaration is invalid."""


class InvalidAsyncAPIMessageError(AsyncAPIDocError, ValueError):
    """Raised when an ``@asyncapi_message`` declaration is invalid."""


class InvalidAsyncAPISecurityError(AsyncAPIDocError, ValueError):
    """Raised when an ``AsyncAPISecurity`` marker is invalid."""


class DuplicateOperationIdError(AsyncAPIDocError, ValueError):
    """Raised when two operations use the same explicit operation ID."""


class DuplicateSecuritySchemeError(AsyncAPIDocError, ValueError):
    """Raised when one security scheme ID has conflicting definitions."""


class MissingYamlDependencyError(AsyncAPIDocError, RuntimeError):
    """Raised when YAML serialization is requested without PyYAML installed."""
