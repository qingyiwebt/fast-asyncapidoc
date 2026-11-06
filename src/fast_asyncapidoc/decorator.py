"""The endpoint decorator and its normalized metadata."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from .errors import InvalidAsyncAPIDecoratorError

EndpointT = TypeVar("EndpointT", bound=Callable[..., Any])
ModelType = type[BaseModel]

_SPECS_ATTRIBUTE = "__fast_asyncapidoc_specs__"


@dataclass(frozen=True)
class OperationSpec:
    """One documented input/output interaction for a WebSocket endpoint."""

    inputs: tuple[ModelType, ...]
    outputs: tuple[ModelType, ...]
    operation_id: str | None = None
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()


def asyncapi(
    *,
    input: ModelType | None = None,
    inputs: Sequence[ModelType] | None = None,
    output: ModelType | None = None,
    outputs: Sequence[ModelType] | None = None,
    operation_id: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    tags: Sequence[str] | None = None,
) -> Callable[[EndpointT], EndpointT]:
    """Attach an AsyncAPI interaction declaration to a WebSocket endpoint.

    ``input`` and ``inputs`` are alternate spellings for a single or multiple
    input models.  ``output`` and ``outputs`` behave the same way.  Either
    side may be omitted for receive-only or server-push documentation, but
    both sides may not be empty.  The decorator intentionally returns the
    original callable instead of wrapping it, so FastAPI sees the original
    signature and dependency metadata.
    """

    normalized_inputs = _normalize_models(
        singular=input,
        plural=inputs,
        singular_name="input",
        plural_name="inputs",
        required=False,
    )
    normalized_outputs = _normalize_models(
        singular=output,
        plural=outputs,
        singular_name="output",
        plural_name="outputs",
        required=False,
    )

    if not normalized_inputs and not normalized_outputs:
        raise InvalidAsyncAPIDecoratorError(
            "at least one input or output model is required"
        )

    normalized_operation_id = _normalize_optional_string(operation_id, "operation_id")
    normalized_title = _normalize_optional_string(title, "title")
    normalized_summary = _normalize_optional_string(summary, "summary")
    normalized_description = _normalize_optional_string(description, "description")
    normalized_tags = _normalize_tags(tags)

    spec = OperationSpec(
        inputs=normalized_inputs,
        outputs=normalized_outputs,
        operation_id=normalized_operation_id,
        title=normalized_title,
        summary=normalized_summary,
        description=normalized_description,
        tags=normalized_tags,
    )

    def decorate(endpoint: EndpointT) -> EndpointT:
        if not callable(endpoint):
            raise InvalidAsyncAPIDecoratorError(
                "@asyncapi can only decorate a callable endpoint"
            )

        existing = list(getattr(endpoint, _SPECS_ATTRIBUTE, ()))
        # Python applies stacked decorators from bottom to top.  Prepending
        # makes generated documentation follow the order visible in source.
        setattr(endpoint, _SPECS_ATTRIBUTE, (spec, *existing))
        return endpoint

    return decorate


def get_operation_specs(endpoint: Any) -> tuple[OperationSpec, ...]:
    """Return declarations attached to an endpoint, if any."""

    candidates = [endpoint]
    try:
        unwrapped = inspect.unwrap(endpoint)
    except (ValueError, TypeError):
        unwrapped = None
    if unwrapped is not None and unwrapped is not endpoint:
        candidates.append(unwrapped)

    for candidate in candidates:
        specs = getattr(candidate, _SPECS_ATTRIBUTE, None)
        if specs is not None:
            return tuple(specs)
    return ()


def _normalize_models(
    *,
    singular: ModelType | None,
    plural: Sequence[ModelType] | None,
    singular_name: str,
    plural_name: str,
    required: bool,
) -> tuple[ModelType, ...]:
    if singular is not None and plural is not None:
        raise InvalidAsyncAPIDecoratorError(
            f"{singular_name!r} and {plural_name!r} are mutually exclusive"
        )

    if singular is not None:
        values: tuple[Any, ...] = (singular,)
    elif plural is not None:
        if isinstance(plural, (str, bytes)):
            raise InvalidAsyncAPIDecoratorError(
                f"{plural_name!r} must be a sequence of Pydantic model classes"
            )
        try:
            values = tuple(plural)
        except TypeError as exc:
            raise InvalidAsyncAPIDecoratorError(
                f"{plural_name!r} must be a sequence of Pydantic model classes"
            ) from exc
    else:
        values = ()

    if required and not values:
        raise InvalidAsyncAPIDecoratorError(
            f"one of {singular_name!r} or {plural_name!r} is required"
        )

    normalized: list[ModelType] = []
    seen: set[ModelType] = set()
    for index, value in enumerate(values):
        if not _is_model_type(value):
            raise InvalidAsyncAPIDecoratorError(
                f"{singular_name if singular is not None else plural_name}[{index}] "
                "must be a Pydantic v2 BaseModel subclass"
            )
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    return tuple(normalized)


def _is_model_type(value: Any) -> bool:
    return isinstance(value, type) and issubclass(value, BaseModel)


def _normalize_optional_string(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidAsyncAPIDecoratorError(f"{name} must be a non-empty string")
    return value


def _normalize_tags(tags: Sequence[str] | None) -> tuple[str, ...]:
    if tags is None:
        return ()
    if isinstance(tags, (str, bytes)):
        raise InvalidAsyncAPIDecoratorError("tags must be a sequence of strings")
    try:
        values = tuple(tags)
    except TypeError as exc:
        raise InvalidAsyncAPIDecoratorError(
            "tags must be a sequence of strings"
        ) from exc
    for index, tag in enumerate(values):
        if not isinstance(tag, str) or not tag.strip():
            raise InvalidAsyncAPIDecoratorError(
                f"tags[{index}] must be a non-empty string"
            )
    return values
