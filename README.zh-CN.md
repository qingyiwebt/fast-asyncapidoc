# fast-asyncapidoc

[English](https://github.com/qingyiwebt/fast-asyncapidoc/blob/main/README.md)

使用 Pydantic v2 模型，为 FastAPI WebSocket endpoint 生成
[AsyncAPI 3.0](https://www.asyncapi.com/docs/reference/specification/v3.0.0)
文档。

## 特性

- 在 endpoint、channel 和 Pydantic 模型附近直接声明协议元数据。
- 支持请求/响应、客户端发送但不响应、服务器主动推送。
- 保留 Pydantic 的 `$defs`、字段描述、枚举和校验约束。
- 支持直接注册的 WebSocket、路由前缀和嵌套路由。
- 从 FastAPI 的 `Query`、`Header`、`Cookie` 参数推断 AsyncAPI 安全方案。
- 支持挂载 JSON 和可选 YAML 文档路由。
- 不包装 endpoint，不影响 FastAPI 依赖注入和原始函数签名。

## 环境要求与安装

- Python 3.10 或更高版本
- FastAPI `>=0.100,<1`
- Pydantic `>=2,<3`

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

from fast_asyncapidoc import (
    AsyncAPIDoc,
    asyncapi_channel,
    asyncapi_message,
    asyncapi_operation,
)


@asyncapi_message(
    title="控制请求",
    description="客户端发送的控制命令。",
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
@asyncapi_channel(description="控制端 WebSocket channel。")
@asyncapi_operation(
    input=ControlRequest,
    output=ControlResponse,
    operation_id="control.request_reply",
    summary="处理控制请求",
)
@asyncapi_operation(
    input=ControlRequest,
    operation_id="control.receive_only",
    summary="处理无响应命令",
)
@asyncapi_operation(
    output=ServerNotice,
    operation_id="control.server_notice",
    summary="接收服务端通知",
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
asyncapi_doc.mount_yaml("/asyncapi.yaml")
```

`mount_yaml()` 需要安装 `yaml` extra。生成的文档可以通过
`GET /asyncapi.json` 和 `GET /asyncapi.yaml` 访问，也可以直接调用
`asyncapi_doc.generate()` 获取 Python `dict`。

## Operation 方向

`input` 和 `output` 仍然相对于 endpoint 函数描述：input 是 endpoint
收到的消息，output 是 endpoint 发出的消息。`AsyncAPIDoc` 默认使用
`perspective="client"`，因此生成的 operation 描述 WebSocket 客户端：

| Endpoint 声明 | 客户端 operation |
| --- | --- |
| `input=Request` | `action: send` |
| `input=Request, output=Response` | `action: send`，带 `reply` |
| `output=Event` | `action: receive` |

如果要描述后端应用本身，可以使用 `perspective="server"`。单个 operation
也可以覆盖自动方向：

```python
@asyncapi_operation(
    output=Event,
    operation_id="special_event",
    action="send",
)
```

只有 output 的声明永远不会生成 `reply`；在客户端视角下，它表示服务端主动
推送的消息。

## Message 元数据

Message 元数据直接挂在 Pydantic 类型上，不再需要生成文档后按 operation ID
查找并修改：

```python
@asyncapi_message(
    title="登录请求",
    description="客户端登录。",
    correlation_id={
        "description": "请求关联值。",
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

同一个模型在多个 operation 中使用时，会复用相同的 message 元数据。
Pydantic 的 `model_config.json_schema_extra` 仍然只用于 schema 级元数据。
其他 AsyncAPI Message Object 字段或 `x-*` 扩展可以放在 `extra={...}` 中。
生成器负责的 `name`、`contentType` 和 `payload` 不允许覆盖。

## 参数级安全方案

使用 `AsyncAPISecurity` 标记 FastAPI 参数后，package 会自动注册安全方案，并
将它应用到该 endpoint 的全部 operation：

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
            description="控制端设备 AppKey。",
        ),
    ] = Query(default=None),
) -> None: ...
```

参数位置从 `Query`、`Header` 或 `Cookie` 推断；如果设置了 alias，则 alias
会作为安全方案的参数名。

## 从 0.1 升级

0.2 是有意的破坏性升级：

- `@asyncapi` 改名为 `@asyncapi_operation`。
- 新增 `@asyncapi_channel` 和 `@asyncapi_message`。
- 默认 perspective 从 `server` 改为 `client`。
- 如需旧的 operation 方向，请设置 `perspective="server"`。

## 开发

本项目使用 uv 管理依赖、锁文件、测试和构建：

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

## 许可证

[MIT License](LICENSE)
