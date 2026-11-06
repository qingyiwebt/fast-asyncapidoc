from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel

from fast_asyncapidoc import (
    InvalidAsyncAPIChannelError,
    InvalidAsyncAPIDecoratorError,
    InvalidAsyncAPIMessageError,
    asyncapi_channel,
    asyncapi_message,
    asyncapi_operation,
)
from fast_asyncapidoc.decorator import (
    get_channel_spec,
    get_message_spec,
    get_operation_specs,
)


class InputA(BaseModel):
    value: int


class InputB(BaseModel):
    value: str


class OutputA(BaseModel):
    result: bool


def test_operation_decorator_keeps_original_callable_and_source_order() -> None:
    @asyncapi_operation(input=InputA, operation_id="first")
    @asyncapi_operation(
        input=InputB,
        output=OutputA,
        operation_id="second",
        action="receive",
    )
    async def endpoint(value: int) -> str:
        return str(value)

    assert inspect.iscoroutinefunction(endpoint)
    specs = get_operation_specs(endpoint)
    assert [spec.operation_id for spec in specs] == ["first", "second"]
    assert specs[0].outputs == ()
    assert specs[1].inputs == (InputB,)
    assert specs[1].outputs == (OutputA,)
    assert specs[1].action == "receive"


def test_plural_models_are_deduplicated() -> None:
    @asyncapi_operation(inputs=[InputA, InputA, InputB], outputs=[OutputA, OutputA])
    async def endpoint() -> None:
        pass

    spec = get_operation_specs(endpoint)[0]
    assert spec.inputs == (InputA, InputB)
    assert spec.outputs == (OutputA,)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"input": InputA, "inputs": [InputB]}, "mutually exclusive"),
        (
            {"input": InputA, "output": OutputA, "outputs": [OutputA]},
            "mutually exclusive",
        ),
        ({}, "at least one input or output"),
        ({"inputs": [], "outputs": []}, "at least one input or output"),
        ({"input": dict}, "Pydantic v2"),
        ({"input": InputA, "tags": "control"}, "sequence of strings"),
        ({"input": InputA, "action": "publish"}, "send.*receive"),
    ],
)
def test_invalid_operation_declarations(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(InvalidAsyncAPIDecoratorError, match=message):
        asyncapi_operation(**kwargs)


def test_output_only_and_empty_input_list_are_valid() -> None:
    @asyncapi_operation(output=OutputA)
    async def output_only() -> None:
        pass

    @asyncapi_operation(inputs=[], outputs=[OutputA])
    async def output_only_with_empty_inputs() -> None:
        pass

    assert get_operation_specs(output_only)[0].inputs == ()
    assert get_operation_specs(output_only)[0].outputs == (OutputA,)
    assert get_operation_specs(output_only_with_empty_inputs)[0].inputs == ()


def test_channel_and_message_decorators_attach_metadata_without_wrapping() -> None:
    @asyncapi_message(
        title="Input message",
        description="A documented input.",
        correlation_id={
            "description": "Request correlation",
            "location": "$message.payload#/echo",
        },
        examples=[{"name": "example", "payload": {"value": 1}}],
        extra={"x-owner": "tests"},
    )
    class DocumentedModel(BaseModel):
        value: int

    @asyncapi_channel(description="A documented channel", tags=["control"])
    @asyncapi_operation(input=DocumentedModel)
    async def endpoint() -> None:
        pass

    assert get_channel_spec(endpoint) is not None
    assert get_channel_spec(endpoint).description == "A documented channel"
    assert get_message_spec(DocumentedModel) is not None
    assert (
        get_message_spec(DocumentedModel).to_document()["correlationId"]["location"]
        == "$message.payload#/echo"
    )


def test_invalid_channel_and_message_declarations() -> None:
    with pytest.raises(InvalidAsyncAPIChannelError, match="address"):
        asyncapi_channel(extra={"address": "/override"})

    with pytest.raises(InvalidAsyncAPIMessageError, match="payload"):
        asyncapi_message(extra={"payload": {"type": "object"}})

    with pytest.raises(InvalidAsyncAPIMessageError, match="BaseModel"):
        asyncapi_message()(dict)  # type: ignore[arg-type]
