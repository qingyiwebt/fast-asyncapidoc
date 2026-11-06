from __future__ import annotations

import json
from typing import Annotated

import pytest
from fastapi import APIRouter, Cookie, FastAPI, Header, Query, WebSocket
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from fast_asyncapidoc import (
    AsyncAPIDoc,
    AsyncAPISecurity,
    DuplicateOperationIdError,
    DuplicateSecuritySchemeError,
    InvalidAsyncAPISecurityError,
    asyncapi_channel,
    asyncapi_message,
    asyncapi_operation,
)


class ControlRequest(BaseModel):
    """A command sent by a connected client."""

    command: str = Field(min_length=1)


class ControlSuccess(BaseModel):
    accepted: bool


class ControlFailure(BaseModel):
    error: str


class NestedPayload(BaseModel):
    value: int


class NestedRequest(BaseModel):
    payload: NestedPayload


def _app_with_router() -> tuple[FastAPI, AsyncAPIDoc]:
    app = FastAPI()
    router = APIRouter()
    doc = AsyncAPIDoc(
        app,
        title="Control API",
        version="1.0.0",
        description="WebSocket documentation",
        servers={"local": {"host": "localhost:8000", "protocol": "ws"}},
    )

    @router.websocket("/control")
    @asyncapi_channel(description="A control channel", tags=["control"])
    @asyncapi_operation(
        input=ControlRequest,
        output=ControlSuccess,
        operation_id="control.one",
        summary="One response",
        description="A command with a single response.",
        tags=["control"],
    )
    @asyncapi_operation(
        input=ControlRequest,
        outputs=[ControlSuccess, ControlFailure],
        operation_id="control.many",
    )
    @asyncapi_operation(input=ControlRequest, operation_id="control.none")
    async def control(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    app.include_router(router, prefix="/api")
    return app, doc


def test_generate_scans_prefixed_lazy_included_router() -> None:
    _, doc = _app_with_router()
    document = doc.generate()

    assert document["asyncapi"] == "3.0.0"
    assert document["defaultContentType"] == "application/json"
    assert document["info"] == {
        "title": "Control API",
        "version": "1.0.0",
        "description": "WebSocket documentation",
    }
    assert document["servers"]["local"]["protocol"] == "ws"

    channel = document["channels"]["api_control"]
    assert channel["address"] == "/api/control"
    assert channel["description"] == "A control channel"
    assert channel["tags"] == [{"name": "control"}]
    assert channel["bindings"]["ws"]["bindingVersion"] == "0.1.0"
    assert len(channel["messages"]) == 3

    operations = document["operations"]
    assert list(operations) == ["control.one", "control.many", "control.none"]
    assert operations["control.one"]["action"] == "send"
    assert operations["control.none"]["action"] == "send"
    assert "reply" not in operations["control.none"]
    assert len(operations["control.one"]["reply"]["messages"]) == 1
    assert len(operations["control.many"]["reply"]["messages"]) == 2
    assert operations["control.one"]["summary"] == "One response"
    assert operations["control.one"]["tags"] == [{"name": "control"}]

    request_schema = document["components"]["schemas"]["ControlRequest"]
    assert request_schema["description"] == "A command sent by a connected client."
    assert request_schema["properties"]["command"]["minLength"] == 1


def test_server_perspective_preserves_endpoint_direction() -> None:
    app = FastAPI()

    @app.websocket("/request")
    @asyncapi_operation(
        input=ControlRequest, output=ControlSuccess, operation_id="request"
    )
    async def request(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    @app.websocket("/events")
    @asyncapi_operation(output=ControlSuccess, operation_id="events")
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    document = AsyncAPIDoc(
        app,
        title="Server",
        version="1",
        perspective="server",
    ).generate()
    assert document["operations"]["request"]["action"] == "receive"
    assert document["operations"]["events"]["action"] == "send"


def test_operation_action_overrides_document_perspective() -> None:
    app = FastAPI()

    @app.websocket("/events")
    @asyncapi_operation(
        output=ControlSuccess,
        operation_id="events",
        action="send",
    )
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    operation = AsyncAPIDoc(app, title="Override", version="1").generate()[
        "operations"
    ]["events"]
    assert operation["action"] == "send"


def test_nested_schema_refs_are_rewritten_to_components() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.websocket("/nested")
    @asyncapi_operation(input=NestedRequest)
    async def nested(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    app.include_router(router)
    document = AsyncAPIDoc(app, title="Nested", version="1").generate()

    nested_schema = document["components"]["schemas"]["NestedRequest"]
    assert nested_schema["properties"]["payload"]["$ref"] == (
        "#/components/schemas/NestedPayload"
    )
    assert "NestedPayload" in document["components"]["schemas"]
    assert "$defs" not in nested_schema


def test_multiple_inputs_and_outputs_are_alternative_messages() -> None:
    app = FastAPI()

    @app.websocket("/multi")
    @asyncapi_operation(
        inputs=[ControlRequest, NestedRequest],
        outputs=[ControlSuccess, ControlFailure],
        operation_id="multi",
    )
    async def multi(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    document = AsyncAPIDoc(app, title="Multi", version="1").generate()
    operation = document["operations"]["multi"]
    assert len(operation["messages"]) == 2
    assert len(operation["reply"]["messages"]) == 2
    assert len(document["channels"]["multi"]["messages"]) == 4


def test_output_only_generates_receive_operation_without_reply() -> None:
    app = FastAPI()

    @app.websocket("/events")
    @asyncapi_operation(
        outputs=[ControlSuccess, ControlFailure],
        operation_id="events",
    )
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    document = AsyncAPIDoc(app, title="Events", version="1").generate()
    operation = document["operations"]["events"]

    assert operation["action"] == "receive"
    assert len(operation["messages"]) == 2
    assert "reply" not in operation
    assert all(
        reference["$ref"].startswith("#/channels/events/messages/")
        for reference in operation["messages"]
    )


def test_empty_inputs_with_outputs_generates_receive_operation() -> None:
    app = FastAPI()

    @app.websocket("/events")
    @asyncapi_operation(inputs=[], output=ControlSuccess, operation_id="events")
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    operation = AsyncAPIDoc(app, title="Events", version="1").generate()["operations"][
        "events"
    ]
    assert operation["action"] == "receive"
    assert len(operation["messages"]) == 1
    assert "reply" not in operation


def test_stacked_operations_cover_all_supported_combinations() -> None:
    app = FastAPI()

    @app.websocket("/all")
    @asyncapi_operation(output=ControlSuccess, operation_id="push")
    @asyncapi_operation(input=ControlRequest, operation_id="receive_only")
    @asyncapi_operation(
        input=ControlRequest,
        output=ControlFailure,
        operation_id="request_reply",
    )
    async def all_combinations(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    operations = AsyncAPIDoc(app, title="All", version="1").generate()["operations"]
    assert list(operations) == ["push", "receive_only", "request_reply"]
    assert operations["push"]["action"] == "receive"
    assert operations["receive_only"]["action"] == "send"
    assert "reply" not in operations["receive_only"]
    assert operations["request_reply"]["action"] == "send"
    assert "reply" in operations["request_reply"]


def test_message_metadata_is_reused_for_every_message_reference() -> None:
    @asyncapi_message(
        title="Documented event",
        description="An event with message metadata.",
        correlation_id={
            "description": "Correlation value",
            "location": "$message.payload#/echo",
        },
        examples=[{"name": "event", "payload": {"value": 1}}],
        extra={"x-owner": "tests"},
    )
    class DocumentedEvent(BaseModel):
        value: int

    app = FastAPI()

    @app.websocket("/events")
    @asyncapi_operation(
        input=DocumentedEvent,
        output=DocumentedEvent,
        operation_id="events",
    )
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    document = AsyncAPIDoc(app, title="Messages", version="1").generate()
    messages = document["components"]["messages"]
    assert messages["events_input_DocumentedEvent"]["title"] == "Documented event"
    assert messages["events_output_DocumentedEvent"]["description"] == (
        "An event with message metadata."
    )
    assert (
        messages["events_input_DocumentedEvent"]["correlationId"]["location"]
        == "$message.payload#/echo"
    )
    assert messages["events_output_DocumentedEvent"]["examples"] == [
        {"name": "event", "payload": {"value": 1}}
    ]
    assert messages["events_input_DocumentedEvent"]["x-owner"] == "tests"


def test_security_markers_infer_query_header_and_cookie() -> None:
    app = FastAPI()

    @app.websocket("/security")
    @asyncapi_operation(input=ControlRequest, operation_id="security")
    async def security(
        websocket: WebSocket,
        query_key: Annotated[
            str | None,
            AsyncAPISecurity(
                scheme_id="queryKey",
                description="Query key",
            ),
        ] = Query(default=None),
        header_key: Annotated[
            str | None,
            AsyncAPISecurity(scheme_id="headerKey"),
        ] = Header(default=None, alias="X-API-Key"),
        cookie_key: Annotated[
            str | None,
            AsyncAPISecurity(scheme_id="cookieKey"),
        ] = Cookie(default=None),
    ) -> None:
        await websocket.accept()
        await websocket.close()

    document = AsyncAPIDoc(app, title="Security", version="1").generate()
    schemes = document["components"]["securitySchemes"]
    assert schemes["queryKey"] == {
        "type": "httpApiKey",
        "name": "query_key",
        "in": "query",
        "description": "Query key",
    }
    assert schemes["headerKey"]["name"] == "X-API-Key"
    assert schemes["headerKey"]["in"] == "header"
    assert schemes["cookieKey"]["name"] == "cookie_key"
    assert schemes["cookieKey"]["in"] == "cookie"
    assert document["operations"]["security"]["security"] == [
        {"$ref": "#/components/securitySchemes/queryKey"},
        {"$ref": "#/components/securitySchemes/headerKey"},
        {"$ref": "#/components/securitySchemes/cookieKey"},
    ]


def test_security_scheme_conflict_fails() -> None:
    app = FastAPI()

    @app.websocket("/one")
    @asyncapi_operation(input=ControlRequest, operation_id="one")
    async def one(
        websocket: WebSocket,
        key: Annotated[str | None, AsyncAPISecurity(scheme_id="shared")] = Query(
            default=None
        ),
    ) -> None:
        pass

    @app.websocket("/two")
    @asyncapi_operation(input=ControlRequest, operation_id="two")
    async def two(
        websocket: WebSocket,
        key: Annotated[
            str | None,
            AsyncAPISecurity(scheme_id="shared", description="different"),
        ] = Query(default=None),
    ) -> None:
        pass

    with pytest.raises(DuplicateSecuritySchemeError, match="shared"):
        AsyncAPIDoc(app, title="Security", version="1").generate()


def test_security_marker_requires_fastapi_parameter_metadata() -> None:
    app = FastAPI()

    @app.websocket("/security")
    @asyncapi_operation(input=ControlRequest, operation_id="security")
    async def security(
        websocket: WebSocket,
        key: Annotated[str | None, AsyncAPISecurity(scheme_id="key")] = None,
    ) -> None:
        pass

    with pytest.raises(InvalidAsyncAPISecurityError, match="Query"):
        AsyncAPIDoc(app, title="Security", version="1").generate()


def test_nested_included_routers_keep_all_prefixes() -> None:
    app = FastAPI()
    child = APIRouter(prefix="/child")
    parent = APIRouter(prefix="/parent")

    @child.websocket("/control")
    @asyncapi_operation(input=ControlRequest, operation_id="nested")
    async def nested(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    parent.include_router(child, prefix="/v1")
    app.include_router(parent, prefix="/api")
    document = AsyncAPIDoc(app, title="Nested", version="1").generate()

    assert document["channels"]["api_parent_v1_child_control"]["address"] == (
        "/api/parent/v1/child/control"
    )


def test_unannotated_websocket_is_ignored_and_document_is_deterministic() -> None:
    app = FastAPI()

    @app.websocket("/ignored")
    async def ignored(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    doc = AsyncAPIDoc(app, title="Test", version="1")
    assert doc.generate()["channels"] == {}
    assert doc.generate() == doc.generate()


def test_same_model_name_is_disambiguated() -> None:
    class SameNameOne(BaseModel):
        a: int

    class SameNameTwo(BaseModel):
        b: str

    SameNameOne.__name__ = "SameName"
    SameNameTwo.__name__ = "SameName"
    app = FastAPI()

    @app.websocket("/one")
    @asyncapi_operation(input=SameNameOne, operation_id="one")
    async def one(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    @app.websocket("/two")
    @asyncapi_operation(input=SameNameTwo, operation_id="two")
    async def two(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    schemas = AsyncAPIDoc(app, title="Test", version="1").generate()["components"][
        "schemas"
    ]
    assert "SameName" in schemas
    assert any(name.startswith("SameName__") for name in schemas)


def test_mount_returns_fresh_json_and_does_not_change_openapi() -> None:
    app, doc = _app_with_router()
    before = app.openapi()
    doc.mount("/asyncapi.json")

    client = TestClient(app)
    response = client.get("/asyncapi.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["asyncapi"] == "3.0.0"
    assert json.loads(response.text) == doc.generate()
    assert app.openapi() == before


def test_mount_yaml_returns_asyncapi_document() -> None:
    yaml = pytest.importorskip("yaml")
    app, doc = _app_with_router()
    doc.mount_yaml("/asyncapi.yaml")

    response = TestClient(app).get("/asyncapi.yaml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/yaml")
    assert yaml.safe_load(response.text) == doc.generate()


def test_websocket_endpoint_still_works_after_decoration() -> None:
    app = FastAPI()

    @app.websocket("/ws")
    @asyncapi_operation(input=ControlRequest)
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"accepted": True})
        await websocket.close()

    with TestClient(app).websocket_connect("/ws") as websocket:
        assert websocket.receive_json() == {"accepted": True}


def test_duplicate_explicit_operation_id_fails() -> None:
    app = FastAPI()

    @app.websocket("/one")
    @asyncapi_operation(input=ControlRequest, operation_id="duplicate")
    async def one(websocket: WebSocket) -> None:
        pass

    @app.websocket("/two")
    @asyncapi_operation(input=ControlRequest, operation_id="duplicate")
    async def two(websocket: WebSocket) -> None:
        pass

    with pytest.raises(DuplicateOperationIdError, match="duplicate"):
        AsyncAPIDoc(app, title="Test", version="1").generate()
