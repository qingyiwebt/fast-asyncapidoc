"""Endpoint, channel, and Pydantic message declarations."""

from __future__ import annotations

import copy
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from .errors import (
    InvalidAsyncAPIChannelError,
    InvalidAsyncAPIDecoratorError,
    InvalidAsyncAPIMessageError,
)

EndpointT = TypeVar("EndpointT", bound=Callable[..., Any])
ModelT = TypeVar("ModelT", bound=type[BaseModel])
ModelType = type[BaseModel]
Action = Literal["send", "receive"]

_OPERATIONS_ATTRIBUTE = "__fast_asyncapidoc_operations__"
_CHANNEL_ATTRIBUTE = "__fast_asyncapidoc_channel__"
_MESSAGE_ATTRIBUTE = "__fast_asyncapidoc_message__"


@dataclass(frozen=True)
class OperationSpec:
    """One documented input/output interaction for a WebSocket endpoint."""

    inputs: tuple[ModelType, ...]
    outputs: tuple[ModelType, ...]
    operation_id: str | None = None
    action: Action | None = None
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChannelSpec:
    """Metadata attached to the channel created for an endpoint."""

    title: str | None = None
    description: str | None = None
    parameters: dict[str, Any] | None = None
    bindings: dict[str, Any] | None = None
    tags: tuple[str, ...] = ()
    external_docs: dict[str, Any] | None = None
    extra: dict[str, Any] | None = None

    def to_document(self) -> dict[str, Any]:
        document: dict[str, Any] = copy.deepcopy(self.extra or {})
        if self.title is not None:
            document["title"] = self.title
        if self.description is not None:
            document["description"] = self.description
        if self.parameters is not None:
            document["parameters"] = copy.deepcopy(self.parameters)
        if self.bindings is not None:
            document["bindings"] = copy.deepcopy(self.bindings)
        if self.tags:
            document["tags"] = [{"name": tag} for tag in self.tags]
        if self.external_docs is not None:
            document["externalDocs"] = copy.deepcopy(self.external_docs)
        return document


@dataclass(frozen=True)
class MessageSpec:
    """Message Object metadata attached to a Pydantic model."""

    title: str | None = None
    summary: str | None = None
    description: str | None = None
    headers: dict[str, Any] | None = None
    correlation_id: dict[str, Any] | None = None
    examples: tuple[dict[str, Any], ...] = ()
    tags: tuple[str, ...] = ()
    external_docs: dict[str, Any] | None = None
    bindings: dict[str, Any] | None = None
    traits: tuple[Any, ...] = ()
    extra: dict[str, Any] | None = None

    def to_document(self) -> dict[str, Any]:
        document: dict[str, Any] = copy.deepcopy(self.extra or {})
        if self.title is not None:
            document["title"] = self.title
        if self.summary is not None:
            document["summary"] = self.summary
        if self.description is not None:
            document["description"] = self.description
        if self.headers is not None:
            document["headers"] = copy.deepcopy(self.headers)
        if self.correlation_id is not None:
            document["correlationId"] = copy.deepcopy(self.correlation_id)
        if self.examples:
            document["examples"] = copy.deepcopy(list(self.examples))
        if self.tags:
            document["tags"] = [{"name": tag} for tag in self.tags]
        if self.external_docs is not None:
            document["externalDocs"] = copy.deepcopy(self.external_docs)
        if self.bindings is not None:
            document["bindings"] = copy.deepcopy(self.bindings)
        if self.traits:
            document["traits"] = copy.deepcopy(list(self.traits))
        return document


def asyncapi_operation(
    *,
    input: ModelType | None = None,
    inputs: Sequence[ModelType] | None = None,
    output: ModelType | None = None,
    outputs: Sequence[ModelType] | None = None,
    operation_id: str | None = None,
    action: Action | None = None,
    title: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    tags: Sequence[str] | None = None,
) -> Callable[[EndpointT], EndpointT]:
    """Attach an AsyncAPI operation declaration to a WebSocket endpoint.

    ``input`` and ``inputs`` are alternate spellings for a single or multiple
    input models. ``output`` and ``outputs`` behave the same way. Either side
    may be omitted, but both sides may not be empty. The decorator returns the
    original callable so FastAPI sees the original signature.
    """

    normalized_inputs = _normalize_models(
        singular=input,
        plural=inputs,
        singular_name="input",
        plural_name="inputs",
        error_type=InvalidAsyncAPIDecoratorError,
    )
    normalized_outputs = _normalize_models(
        singular=output,
        plural=outputs,
        singular_name="output",
        plural_name="outputs",
        error_type=InvalidAsyncAPIDecoratorError,
    )

    if not normalized_inputs and not normalized_outputs:
        raise InvalidAsyncAPIDecoratorError(
            "at least one input or output model is required"
        )

    normalized_operation_id = _normalize_optional_string(
        operation_id, "operation_id", InvalidAsyncAPIDecoratorError
    )
    normalized_action = _normalize_action(action)
    normalized_title = _normalize_optional_string(
        title, "title", InvalidAsyncAPIDecoratorError
    )
    normalized_summary = _normalize_optional_string(
        summary, "summary", InvalidAsyncAPIDecoratorError
    )
    normalized_description = _normalize_optional_string(
        description, "description", InvalidAsyncAPIDecoratorError
    )
    normalized_tags = _normalize_tags(tags, InvalidAsyncAPIDecoratorError)

    spec = OperationSpec(
        inputs=normalized_inputs,
        outputs=normalized_outputs,
        operation_id=normalized_operation_id,
        action=normalized_action,
        title=normalized_title,
        summary=normalized_summary,
        description=normalized_description,
        tags=normalized_tags,
    )

    def decorate(endpoint: EndpointT) -> EndpointT:
        if not callable(endpoint):
            raise InvalidAsyncAPIDecoratorError(
                "@asyncapi_operation can only decorate a callable endpoint"
            )

        existing = list(getattr(endpoint, _OPERATIONS_ATTRIBUTE, ()))
        # Python applies stacked decorators from bottom to top. Prepending
        # makes generated documentation follow the order visible in source.
        setattr(endpoint, _OPERATIONS_ATTRIBUTE, (spec, *existing))
        return endpoint

    return decorate


def asyncapi_channel(
    *,
    title: str | None = None,
    description: str | None = None,
    parameters: Mapping[str, Any] | None = None,
    bindings: Mapping[str, Any] | None = None,
    tags: Sequence[str] | None = None,
    external_docs: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Callable[[EndpointT], EndpointT]:
    """Attach channel metadata to a WebSocket endpoint."""

    normalized_extra = _normalize_mapping(
        extra,
        "extra",
        InvalidAsyncAPIChannelError,
    )
    _reject_reserved_keys(
        normalized_extra,
        {"address", "messages"},
        "extra",
        InvalidAsyncAPIChannelError,
    )
    spec = ChannelSpec(
        title=_normalize_optional_string(title, "title", InvalidAsyncAPIChannelError),
        description=_normalize_optional_string(
            description, "description", InvalidAsyncAPIChannelError
        ),
        parameters=_normalize_mapping(
            parameters,
            "parameters",
            InvalidAsyncAPIChannelError,
        ),
        bindings=_normalize_mapping(
            bindings,
            "bindings",
            InvalidAsyncAPIChannelError,
        ),
        tags=_normalize_tags(tags, InvalidAsyncAPIChannelError),
        external_docs=_normalize_mapping(
            external_docs,
            "external_docs",
            InvalidAsyncAPIChannelError,
        ),
        extra=normalized_extra,
    )

    def decorate(endpoint: EndpointT) -> EndpointT:
        if not callable(endpoint):
            raise InvalidAsyncAPIChannelError(
                "@asyncapi_channel can only decorate a callable endpoint"
            )
        if getattr(endpoint, _CHANNEL_ATTRIBUTE, None) is not None:
            raise InvalidAsyncAPIChannelError(
                "only one @asyncapi_channel declaration is allowed per endpoint"
            )
        setattr(endpoint, _CHANNEL_ATTRIBUTE, spec)
        return endpoint

    return decorate


def asyncapi_message(
    *,
    title: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    headers: Mapping[str, Any] | None = None,
    correlation_id: Mapping[str, Any] | None = None,
    examples: Sequence[Mapping[str, Any]] | None = None,
    tags: Sequence[str] | None = None,
    external_docs: Mapping[str, Any] | None = None,
    bindings: Mapping[str, Any] | None = None,
    traits: Sequence[Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Callable[[ModelT], ModelT]:
    """Attach AsyncAPI Message Object metadata to a Pydantic model."""

    normalized_extra = _normalize_mapping(
        extra,
        "extra",
        InvalidAsyncAPIMessageError,
    )
    _reject_reserved_keys(
        normalized_extra,
        {"name", "contentType", "payload"},
        "extra",
        InvalidAsyncAPIMessageError,
    )
    spec = MessageSpec(
        title=_normalize_optional_string(title, "title", InvalidAsyncAPIMessageError),
        summary=_normalize_optional_string(
            summary, "summary", InvalidAsyncAPIMessageError
        ),
        description=_normalize_optional_string(
            description, "description", InvalidAsyncAPIMessageError
        ),
        headers=_normalize_mapping(
            headers,
            "headers",
            InvalidAsyncAPIMessageError,
        ),
        correlation_id=_normalize_mapping(
            correlation_id,
            "correlation_id",
            InvalidAsyncAPIMessageError,
        ),
        examples=_normalize_examples(examples),
        tags=_normalize_tags(tags, InvalidAsyncAPIMessageError),
        external_docs=_normalize_mapping(
            external_docs,
            "external_docs",
            InvalidAsyncAPIMessageError,
        ),
        bindings=_normalize_mapping(
            bindings,
            "bindings",
            InvalidAsyncAPIMessageError,
        ),
        traits=_normalize_values(traits, "traits", InvalidAsyncAPIMessageError),
        extra=normalized_extra,
    )

    def decorate(model: ModelT) -> ModelT:
        if not _is_model_type(model):
            raise InvalidAsyncAPIMessageError(
                "@asyncapi_message can only decorate a Pydantic v2 BaseModel subclass"
            )
        if getattr(model, _MESSAGE_ATTRIBUTE, None) is not None:
            raise InvalidAsyncAPIMessageError(
                "only one @asyncapi_message declaration is allowed per model"
            )
        setattr(model, _MESSAGE_ATTRIBUTE, spec)
        return model

    return decorate


def get_operation_specs(endpoint: Any) -> tuple[OperationSpec, ...]:
    """Return operation declarations attached to an endpoint, if any."""

    for candidate in _metadata_candidates(endpoint):
        specs = getattr(candidate, _OPERATIONS_ATTRIBUTE, None)
        if specs is not None:
            return tuple(specs)
    return ()


def get_channel_spec(endpoint: Any) -> ChannelSpec | None:
    """Return channel metadata attached to an endpoint, if any."""

    for candidate in _metadata_candidates(endpoint):
        spec = getattr(candidate, _CHANNEL_ATTRIBUTE, None)
        if spec is not None:
            return spec
    return None


def get_message_spec(model: Any) -> MessageSpec | None:
    """Return message metadata attached to a Pydantic model, if any."""

    return getattr(model, _MESSAGE_ATTRIBUTE, None)


def _metadata_candidates(value: Any) -> list[Any]:
    candidates = [value]
    try:
        unwrapped = inspect.unwrap(value)
    except (ValueError, TypeError):
        unwrapped = None
    if unwrapped is not None and unwrapped is not value:
        candidates.append(unwrapped)
    return candidates


def _normalize_models(
    *,
    singular: ModelType | None,
    plural: Sequence[ModelType] | None,
    singular_name: str,
    plural_name: str,
    error_type: type[ValueError],
) -> tuple[ModelType, ...]:
    if singular is not None and plural is not None:
        raise error_type(
            f"{singular_name!r} and {plural_name!r} are mutually exclusive"
        )

    if singular is not None:
        values: tuple[Any, ...] = (singular,)
    elif plural is not None:
        if isinstance(plural, (str, bytes)):
            raise error_type(
                f"{plural_name!r} must be a sequence of Pydantic model classes"
            )
        try:
            values = tuple(plural)
        except TypeError as exc:
            raise error_type(
                f"{plural_name!r} must be a sequence of Pydantic model classes"
            ) from exc
    else:
        values = ()

    normalized: list[ModelType] = []
    seen: set[ModelType] = set()
    for index, value in enumerate(values):
        if not _is_model_type(value):
            raise error_type(
                f"{singular_name if singular is not None else plural_name}[{index}] "
                "must be a Pydantic v2 BaseModel subclass"
            )
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    return tuple(normalized)


def _is_model_type(value: Any) -> bool:
    return isinstance(value, type) and issubclass(value, BaseModel)


def _normalize_action(action: Action | None) -> Action | None:
    if action is None:
        return None
    if action not in {"send", "receive"}:
        raise InvalidAsyncAPIDecoratorError("action must be either 'send' or 'receive'")
    return action


def _normalize_optional_string(
    value: str | None,
    name: str,
    error_type: type[ValueError],
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{name} must be a non-empty string")
    return value


def _normalize_tags(
    tags: Sequence[str] | None,
    error_type: type[ValueError],
) -> tuple[str, ...]:
    if tags is None:
        return ()
    if isinstance(tags, (str, bytes)):
        raise error_type("tags must be a sequence of strings")
    try:
        values = tuple(tags)
    except TypeError as exc:
        raise error_type("tags must be a sequence of strings") from exc
    for index, tag in enumerate(values):
        if not isinstance(tag, str) or not tag.strip():
            raise error_type(f"tags[{index}] must be a non-empty string")
    return values


def _normalize_mapping(
    value: Mapping[str, Any] | None,
    name: str,
    error_type: type[ValueError],
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise error_type(f"{name} must be a mapping")
    for key in value:
        if not isinstance(key, str) or not key:
            raise error_type(f"{name} keys must be non-empty strings")
    return copy.deepcopy(dict(value))


def _normalize_examples(
    examples: Sequence[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], ...]:
    if examples is None:
        return ()
    if isinstance(examples, (str, bytes)):
        raise InvalidAsyncAPIMessageError("examples must be a sequence of mappings")
    try:
        values = tuple(examples)
    except TypeError as exc:
        raise InvalidAsyncAPIMessageError(
            "examples must be a sequence of mappings"
        ) from exc
    normalized: list[dict[str, Any]] = []
    for index, example in enumerate(values):
        if not isinstance(example, Mapping):
            raise InvalidAsyncAPIMessageError(f"examples[{index}] must be a mapping")
        normalized.append(copy.deepcopy(dict(example)))
    return tuple(normalized)


def _normalize_values(
    values: Sequence[Any] | None,
    name: str,
    error_type: type[ValueError],
) -> tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise error_type(f"{name} must be a sequence")
    try:
        return tuple(copy.deepcopy(values))
    except TypeError as exc:
        raise error_type(f"{name} must be a sequence") from exc


def _reject_reserved_keys(
    value: Mapping[str, Any] | None,
    reserved: set[str],
    name: str,
    error_type: type[ValueError],
) -> None:
    if value is None:
        return
    conflict = sorted(reserved.intersection(value))
    if conflict:
        joined = ", ".join(conflict)
        raise error_type(f"{name} cannot override generated fields: {joined}")
