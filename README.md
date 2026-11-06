# fast-asyncapidoc

[简体中文](https://github.com/qingyiwebt/fast-asyncapidoc/blob/main/README.zh-CN.md)

Generate [AsyncAPI 3.0](https://www.asyncapi.com/docs/reference/specification/v3.0.0)
documentation for [FastAPI](https://fastapi.tiangolo.com/) WebSocket endpoints
using [Pydantic v2](https://docs.pydantic.dev/latest/).

## Features

- Describe WebSocket messages with repeatable `@asyncapi` decorators.
- Generate AsyncAPI channels, operations, messages, and Pydantic schemas.
- Document request/reply, receive-only, and server-push interactions.
- Discover routes from direct FastAPI routes, routers, prefixes, and nested routers.
- Mount the generated document at a JSON endpoint or export it as a Python `dict`.
- Optionally serialize the document as YAML.
- Keep endpoint functions unchanged, including their FastAPI dependency signatures.

## Requirements

- Python 3.10 or newer
- FastAPI `>=0.100,<1`
- Pydantic `>=2,<3`

## Installation

Install the package with uv:

```bash
uv add fast-asyncapidoc
```

Install optional YAML support when needed:

```bash
uv add "fast-asyncapidoc[yaml]"
```

## Quick start

```python
from fastapi import APIRouter, FastAPI, WebSocket
from pydantic import BaseModel

from fast_asyncapidoc import AsyncAPIDoc, asyncapi


class ControlRequest(BaseModel):
    command: str


class ControlSuccess(BaseModel):
    accepted: bool


class ControlFailure(BaseModel):
    error: str


class ServerNotice(BaseModel):
    message: str


router = APIRouter()


@router.websocket("/control")
@asyncapi(
    input=ControlRequest,
    output=ControlSuccess,
    operation_id="control.request_reply",
    summary="Handle a control request",
)
@asyncapi(
    input=ControlRequest,
    outputs=[ControlSuccess, ControlFailure],
    operation_id="control.result",
)
@asyncapi(
    input=ControlRequest,
    operation_id="control.receive_only",
)
@asyncapi(
    output=ServerNotice,
    operation_id="control.server_notice",
)
async def control(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.close()


app = FastAPI()
app.include_router(router, prefix="/api")

asyncapi_doc = AsyncAPIDoc(
    app,
    title="Control API",
    version="1.0.0",
    description="WebSocket API documentation",
    servers={
        "development": {
            "host": "localhost:8000",
            "protocol": "ws",
        }
    },
)
asyncapi_doc.mount("/asyncapi.json")
```

The generated document is available at `GET /asyncapi.json` and can also be
obtained directly:

```python
document: dict = asyncapi_doc.generate()
```

## Decorator semantics

`@asyncapi` accepts either a singular or plural form for each direction:

```python
@asyncapi(input=Request)
@asyncapi(inputs=[RequestA, RequestB])
@asyncapi(output=Response)
@asyncapi(outputs=[Success, Failure])
```

The supported combinations are:

| Inputs | Outputs | AsyncAPI operation |
| --- | --- | --- |
| One or more | None | `action: receive`, without `reply` |
| One or more | One or more | `action: receive`, with `reply` |
| None | One or more | `action: send`, for server push |

An empty declaration is invalid. `input` and `inputs` cannot be used together,
and the same applies to `output` and `outputs`.

The decorator supports the following operation metadata:

- `operation_id`: explicit key in the AsyncAPI `operations` map.
- `title`, `summary`, `description`: operation documentation.
- `tags`: operation grouping tags.

The message payload schema is generated from each Pydantic model's
`model_json_schema()` output. The package documents message contracts; it does
not parse, validate, or transform runtime WebSocket frames.

## YAML export

After installing the `yaml` extra:

```python
yaml_document = asyncapi_doc.to_yaml()
```

## Development

This repository uses uv for dependency management and builds:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

## Links

- [AsyncAPI 3.0 specification](https://www.asyncapi.com/docs/reference/specification/v3.0.0)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Pydantic](https://docs.pydantic.dev/latest/)
- [uv](https://docs.astral.sh/uv/)
- [Repository](https://github.com/qingyiwebt/fast-asyncapidoc)

## License

[MIT License](LICENSE)
