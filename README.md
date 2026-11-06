# fast-asyncapidoc

Generate AsyncAPI 3.0 documentation for FastAPI WebSocket endpoints using
Pydantic v2 models.

## Usage

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


router = APIRouter()


@router.websocket("/control")
@asyncapi(
    input=ControlRequest,
    outputs=[ControlSuccess, ControlFailure],
    operation_id="control",
    summary="Control the connected device",
    tags=["control"],
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
    servers={
        "development": {
            "host": "localhost:8000",
            "protocol": "ws",
        }
    },
)
asyncapi_doc.mount("/asyncapi.json")
```

服务器主动推送可以只声明输出模型。此时生成的 operation 使用
`action: send`，输出消息直接放在 operation 的 `messages` 中：

```python
@router.websocket("/events")
@asyncapi(outputs=[ControlSuccess, ControlFailure], operation_id="events")
async def events(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"accepted": True})
```

也可以声明 `@asyncapi(input=Request)` 表示接收消息但不回应，或同时声明
输入和输出表示 request/reply。

`asyncapi_doc.generate()` returns the document as a Python dictionary. The
optional YAML serializer is available with:

```bash
uv add --optional yaml PyYAML
```

```python
yaml_document = asyncapi_doc.to_yaml()
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv build
```
