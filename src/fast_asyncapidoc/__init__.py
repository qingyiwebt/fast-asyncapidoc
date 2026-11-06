"""Generate AsyncAPI 3 documentation for FastAPI WebSocket endpoints."""

from .decorator import (
    ChannelSpec,
    MessageSpec,
    OperationSpec,
    asyncapi_channel,
    asyncapi_message,
    asyncapi_operation,
)
from .document import AsyncAPIDoc
from .errors import (
    AsyncAPIDocError,
    DuplicateOperationIdError,
    DuplicateSecuritySchemeError,
    InvalidAsyncAPIChannelError,
    InvalidAsyncAPIDecoratorError,
    InvalidAsyncAPIMessageError,
    InvalidAsyncAPISecurityError,
    MissingYamlDependencyError,
)
from .security import AsyncAPISecurity

__all__ = [
    "AsyncAPIDoc",
    "AsyncAPIDocError",
    "AsyncAPISecurity",
    "ChannelSpec",
    "DuplicateOperationIdError",
    "DuplicateSecuritySchemeError",
    "InvalidAsyncAPIChannelError",
    "InvalidAsyncAPIDecoratorError",
    "InvalidAsyncAPIMessageError",
    "InvalidAsyncAPISecurityError",
    "MessageSpec",
    "MissingYamlDependencyError",
    "OperationSpec",
    "asyncapi_channel",
    "asyncapi_message",
    "asyncapi_operation",
]
