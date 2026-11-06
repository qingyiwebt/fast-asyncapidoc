from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel

from fast_asyncapidoc import InvalidAsyncAPIDecoratorError, asyncapi
from fast_asyncapidoc.decorator import get_operation_specs


class InputA(BaseModel):
    value: int


class InputB(BaseModel):
    value: str


class OutputA(BaseModel):
    result: bool


def test_decorator_keeps_original_callable_and_source_order() -> None:
    @asyncapi(input=InputA, operation_id="first")
    @asyncapi(input=InputB, output=OutputA, operation_id="second")
    async def endpoint(value: int) -> str:
        return str(value)

    assert inspect.iscoroutinefunction(endpoint)
    specs = get_operation_specs(endpoint)
    assert [spec.operation_id for spec in specs] == ["first", "second"]
    assert specs[0].outputs == ()
    assert specs[1].inputs == (InputB,)
    assert specs[1].outputs == (OutputA,)


def test_plural_models_are_deduplicated() -> None:
    @asyncapi(inputs=[InputA, InputA, InputB], outputs=[OutputA, OutputA])
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
    ],
)
def test_invalid_declarations(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(InvalidAsyncAPIDecoratorError, match=message):
        asyncapi(**kwargs)


def test_output_only_and_empty_input_list_are_valid() -> None:
    @asyncapi(output=OutputA)
    async def output_only() -> None:
        pass

    @asyncapi(inputs=[], outputs=[OutputA])
    async def output_only_with_empty_inputs() -> None:
        pass

    assert get_operation_specs(output_only)[0].inputs == ()
    assert get_operation_specs(output_only)[0].outputs == (OutputA,)
    assert get_operation_specs(output_only_with_empty_inputs)[0].inputs == ()
