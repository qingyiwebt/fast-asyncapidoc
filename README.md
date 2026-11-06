# fast-asyncapidoc

[简体中文](https://github.com/qingyiwebt/fast-asyncapidoc/blob/main/README.zh-CN.md)

Generate [AsyncAPI 3.0](https://www.asyncapi.com/docs/reference/specification/v3.0.0)
documentation for FastAPI WebSocket endpoints using Pydantic v2 models.

## Features

- Describe operations, channels, and messages next to the code that implements them.
- Support request/reply, client messages without replies, and server-pushed messages.
- Generate Pydantic schemas without losing `$defs`, descriptions, enums, or constraints.
- Discover direct WebSocket routes, router prefixes, and nested routers.
- Infer AsyncAPI security schemes from FastAPI `Query`, `Header`, and `Cookie` parameters.
- Mount JSON and optional YAML documents without changing the endpoint signature.
- Keep the original endpoint callable so FastAPI dependency injection continues to work.

## Requirements and installation

- Python 3.10+
- FastAPI `>=0.100,<1`
- Pydantic `>=2,<3`

```bash
uv add fast-asyncapidoc
```

Install YAML support when needed:

```bash
uv add "fast-asyncapidoc[yaml]"
```

## Quick start

```python
from fastapi import APIRouter, FastAPI, WebSocket
from pydantic import BaseModel

from fast_asyncapidoc import (
    AsyncAPIDoc,
    asyncapi_channel,
    asyncapi_message,
    asyncapi_operation,
)


@asyncapi_message(
    title="Control request",
    description="A command sent by the client.",
    examples=[{"name": "status", "payload": {"command": "status"}}],
)
class ControlRequest(BaseModel):
    command: str


class ControlResponse(BaseModel):
    accepted: bool


class ServerNotice(BaseModel):
    message: str


router = APIRouter()


@router.websocket("/control")
@asyncapi_channel(description="The control WebSocket channel.")
@asyncapi_operation(
    input=ControlRequest,
    output=ControlResponse,
    operation_id="control.request_reply",
    summary="Handle a control request",
)
@asyncapi_operation(
    input=ControlRequest,
    operation_id="control.receive_only",
    summary="Handle a command without a response",
)
@asyncapi_operation(
    output=ServerNotice,
    operation_id="control.server_notice",
    summary="Receive a server notice",
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
asyncapi_doc.mount_yaml("/asyncapi.yaml")
```

`mount_yaml()` requires the `yaml` extra. The generated documents are available at
`GET /asyncapi.json` and `GET /asyncapi.yaml`; the dictionary is also available
directly through `asyncapi_doc.generate()`.

## Operation direction

`input` and `output` describe messages relative to the endpoint function:
inputs are received by the endpoint and outputs are sent by it. The
`AsyncAPIDoc` default is `perspective="client"`, so the generated operation
describes the WebSocket client:

| Endpoint declaration | Client operation |
| --- | --- |
| `input=Request` | `action: send` |
| `input=Request, output=Response` | `action: send` with `reply` |
| `output=Event` | `action: receive` |

Use `perspective="server"` to document the backend application instead. An
individual operation can override the perspective mapping:

```python
@asyncapi_operation(
    output=Event,
    operation_id="special_event",
    action="send",
)
```

An output-only declaration never creates a `reply`; it represents a one-way
server push in the client perspective.

## Message metadata

Message metadata belongs on the Pydantic type, not in a post-processing map:

```python
@asyncapi_message(
    title="Login request",
    description="Authenticate a client.",
    correlation_id={
        "description": "Request correlation value.",
        "location": "$message.payload#/echo",
    },
    examples=[
        {
            "name": "login",
            "payload": {"type": "login", "access_token": "<JWT>"},
        }
    ],
)
class LoginRequest(BaseModel):
    type: str
    access_token: str
```

The metadata is reused wherever the model appears as a message. Pydantic's
`model_config.json_schema_extra` remains the place for schema-level metadata.
Use `extra={...}` for additional AsyncAPI Message Object fields or `x-*`
extensions. Generated `name`, `contentType`, and `payload` fields cannot be
overridden.

## Parameter-level security

Mark a FastAPI parameter with `AsyncAPISecurity` to register a security scheme
and apply it to every documented operation on that endpoint:

```python
from typing import Annotated

from fastapi import Query
from fast_asyncapidoc import AsyncAPISecurity


async def control(
    websocket: WebSocket,
    appkey: Annotated[
        str | None,
        AsyncAPISecurity(
            scheme_id="controlAppKey",
            description="The device AppKey.",
        ),
    ] = Query(default=None),
) -> None: ...
```

The parameter location is inferred from `Query`, `Header`, or `Cookie`; an
explicit alias is used as the security scheme name.

## Upgrade from 0.1

Version 0.2 intentionally has breaking changes:

- Rename `@asyncapi` to `@asyncapi_operation`.
- Add `@asyncapi_channel` and `@asyncapi_message` for in-code metadata.
- The default perspective changes from `server` to `client`.
- Use `perspective="server"` to retain the old operation direction.

## Development

This project uses uv for dependencies, locking, testing, and building:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

## License

[MIT License](LICENSE)
