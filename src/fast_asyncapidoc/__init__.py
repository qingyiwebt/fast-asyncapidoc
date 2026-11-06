"""Generate AsyncAPI 3 documentation for FastAPI WebSocket endpoints."""

from .decorator import OperationSpec, asyncapi
from .document import AsyncAPIDoc
from .errors import (
    AsyncAPIDocError,
    DuplicateOperationIdError,
    InvalidAsyncAPIDecoratorError,
    MissingYamlDependencyError,
)

__all__ = [
    "AsyncAPIDoc",
    "AsyncAPIDocError",
    "DuplicateOperationIdError",
    "InvalidAsyncAPIDecoratorError",
    "MissingYamlDependencyError",
    "OperationSpec",
    "asyncapi",
]
