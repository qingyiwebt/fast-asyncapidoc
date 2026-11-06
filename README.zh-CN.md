# fast-asyncapidoc

[English](README.md)

使用 [Pydantic v2](https://docs.pydantic.dev/latest/) 模型，为
[FastAPI](https://fastapi.tiangolo.com/) WebSocket endpoint 生成
[AsyncAPI 3.0](https://www.asyncapi.com/docs/reference/specification/v3.0.0)
文档。

## 特性

- 使用可重复的 `@asyncapi` 装饰器描述 WebSocket 消息。
- 自动生成 AsyncAPI channels、operations、messages 和 Pydantic schemas。
- 支持请求/响应、只接收消息和服务器主动推送。
- 支持直接注册的 WebSocket、APIRouter、路由前缀和嵌套路由。
- 可挂载 JSON 文档路由，也可直接导出 Python `dict`。
- 可选导出 YAML 文档。
- 不包装 endpoint，不影响 FastAPI 依赖注入和函数签名。

## 环境要求

- Python 3.10 或更高版本
- FastAPI `>=0.100,<1`
- Pydantic `>=2,<3`

## 安装

使用 uv 安装：

```bash
uv add fast-asyncapidoc
```

需要 YAML 支持时安装可选依赖：

```bash
uv add "fast-asyncapidoc[yaml]"
```

## 快速开始

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
    summary="处理控制请求",
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
    description="WebSocket API 文档",
    servers={
        "development": {
            "host": "localhost:8000",
            "protocol": "ws",
        }
    },
)
asyncapi_doc.mount("/asyncapi.json")
```

生成的文档可以通过 `GET /asyncapi.json` 访问，也可以直接获取：

```python
document: dict = asyncapi_doc.generate()
```

## 装饰器语义

输入和输出都支持单数或复数形式：

```python
@asyncapi(input=Request)
@asyncapi(inputs=[RequestA, RequestB])
@asyncapi(output=Response)
@asyncapi(outputs=[Success, Failure])
```

支持以下组合：

| 输入 | 输出 | AsyncAPI operation |
| --- | --- | --- |
| 一个或多个 | 无 | `action: receive`，不生成 `reply` |
| 一个或多个 | 一个或多个 | `action: receive`，生成 `reply` |
| 无 | 一个或多个 | `action: send`，表示服务器主动推送 |

输入和输出同时为空的声明无效。`input` 和 `inputs` 不能同时使用，
`output` 和 `outputs` 也不能同时使用。

装饰器支持以下 operation 元数据：

- `operation_id`：AsyncAPI `operations` map 中的显式 key。
- `title`、`summary`、`description`：operation 文档信息。
- `tags`：operation 分组标签。

消息 payload schema 直接来自 Pydantic 模型的
`model_json_schema()`。本项目只负责生成消息契约，不会解析、校验或转换
运行时 WebSocket frame。

## YAML 导出

安装 `yaml` 可选依赖后：

```python
yaml_document = asyncapi_doc.to_yaml()
```

## 开发

本项目使用 uv 管理依赖和构建：

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

## 相关链接

- [AsyncAPI 3.0 规范](https://www.asyncapi.com/docs/reference/specification/v3.0.0)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Pydantic](https://docs.pydantic.dev/latest/)
- [uv](https://docs.astral.sh/uv/)
- [项目仓库](https://github.com/qingyiwebt/fast-asyncapidoc)

## 许可证

[MIT License](LICENSE)
