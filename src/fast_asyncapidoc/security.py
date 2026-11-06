"""Parameter-level security metadata for FastAPI WebSocket endpoints."""

from __future__ import annotations

import copy
import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal, get_args, get_origin, get_type_hints

from fastapi.params import Cookie, Header, Query

from .errors import InvalidAsyncAPISecurityError

SecurityLocation = Literal["query", "header", "cookie"]
_FIELD_INFO_TYPES = (Query, Header, Cookie)


@dataclass(frozen=True)
class AsyncAPISecurity:
    """Mark a FastAPI parameter as an AsyncAPI security scheme.

    The parameter's ``Query``, ``Header``, or ``Cookie`` declaration provides
    the default security location and external name. Explicit values supplied
    here take precedence.
    """

    scheme_id: str
    description: str | None = None
    type: str = "httpApiKey"
    name: str | None = None
    in_: SecurityLocation | None = None
    extra: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_string(self.scheme_id, "scheme_id")
        _validate_non_empty_string(self.type, "type")
        if self.description is not None:
            _validate_non_empty_string(self.description, "description")
        if self.name is not None:
            _validate_non_empty_string(self.name, "name")
        if self.in_ is not None and self.in_ not in {
            "query",
            "header",
            "cookie",
        }:
            raise InvalidAsyncAPISecurityError(
                "in_ must be one of 'query', 'header', or 'cookie'"
            )
        if self.extra is not None:
            if not isinstance(self.extra, Mapping):
                raise InvalidAsyncAPISecurityError("extra must be a mapping")
            conflict = {"type", "name", "in"}.intersection(self.extra)
            if conflict:
                joined = ", ".join(sorted(conflict))
                raise InvalidAsyncAPISecurityError(
                    f"extra cannot override security fields: {joined}"
                )
            object.__setattr__(self, "extra", copy.deepcopy(dict(self.extra)))

    def to_scheme(
        self,
        parameter_name: str,
        field_info: Any,
    ) -> dict[str, Any]:
        location = self.in_ or _infer_location(field_info)
        name = self.name or _infer_name(parameter_name, field_info, location)
        scheme: dict[str, Any] = {
            "type": self.type,
            "name": name,
            "in": location,
        }
        if self.description is not None:
            scheme["description"] = self.description
        if self.extra is not None:
            scheme.update(copy.deepcopy(dict(self.extra)))
        return scheme


def get_security_schemes(
    endpoint: Any,
) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Collect security scheme declarations from endpoint parameters."""

    try:
        signature = inspect.signature(endpoint)
    except (TypeError, ValueError):
        return ()

    try:
        hints = get_type_hints(endpoint, include_extras=True)
    except (NameError, TypeError, ValueError):
        hints = {}

    declarations: list[tuple[str, dict[str, Any]]] = []
    for parameter in signature.parameters.values():
        annotation = hints.get(parameter.name, parameter.annotation)
        metadata = _annotated_metadata(annotation)
        markers = [item for item in metadata if isinstance(item, AsyncAPISecurity)]
        if not markers:
            continue

        field_info = _find_field_info(parameter.default, metadata)
        if field_info is None:
            raise InvalidAsyncAPISecurityError(
                f"security parameter {parameter.name!r} must use Query, Header, "
                "or Cookie"
            )
        for marker in markers:
            declarations.append(
                (
                    marker.scheme_id,
                    marker.to_scheme(parameter.name, field_info),
                )
            )
    return tuple(declarations)


def _annotated_metadata(annotation: Any) -> tuple[Any, ...]:
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *metadata = get_args(annotation)
        return tuple(metadata) + _annotated_metadata(base)
    metadata: list[Any] = []
    for argument in get_args(annotation):
        metadata.extend(_annotated_metadata(argument))
    return tuple(metadata)


def _find_field_info(default: Any, metadata: tuple[Any, ...]) -> Any | None:
    if isinstance(default, _FIELD_INFO_TYPES):
        return default
    for item in metadata:
        if isinstance(item, _FIELD_INFO_TYPES):
            return item
    return None


def _infer_location(field_info: Any) -> SecurityLocation:
    if isinstance(field_info, Query):
        return "query"
    if isinstance(field_info, Header):
        return "header"
    if isinstance(field_info, Cookie):
        return "cookie"
    raise InvalidAsyncAPISecurityError(
        "security parameter must use Query, Header, or Cookie"
    )


def _infer_name(
    parameter_name: str,
    field_info: Any,
    location: SecurityLocation,
) -> str:
    alias = getattr(field_info, "alias", None)
    if isinstance(alias, str) and alias:
        return alias
    if location == "header":
        return parameter_name.replace("_", "-")
    return parameter_name


def _validate_non_empty_string(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidAsyncAPISecurityError(f"{name} must be a non-empty string")
