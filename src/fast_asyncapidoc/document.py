"""AsyncAPI 3 document generation and optional FastAPI mounting."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

from .decorator import (
    OperationSpec,
    get_channel_spec,
    get_message_spec,
    get_operation_specs,
)
from .errors import (
    DuplicateOperationIdError,
    DuplicateSecuritySchemeError,
    InvalidAsyncAPIChannelError,
    MissingYamlDependencyError,
)
from .scanner import WebSocketRouteInfo, iter_websocket_routes
from .security import get_security_schemes

_ASYNCAPI_VERSION = "3.0.0"
_JSON_CONTENT_TYPE = "application/json"
_WEBSOCKET_BINDING_VERSION = "0.1.0"
_KEY_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
Perspective = Literal["client", "server"]


class AsyncAPIDoc:
    """Generate AsyncAPI 3 documentation from a FastAPI application."""

    def __init__(
        self,
        app: FastAPI,
        *,
        title: str,
        version: str,
        description: str | None = None,
        servers: Mapping[str, Mapping[str, Any]] | None = None,
        perspective: Perspective = "client",
    ) -> None:
        if not hasattr(app, "routes") or not hasattr(app, "add_api_route"):
            raise TypeError("app must be a FastAPI application")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title must be a non-empty string")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("version must be a non-empty string")
        if description is not None and not isinstance(description, str):
            raise TypeError("description must be a string or None")
        if perspective not in {"client", "server"}:
            raise ValueError("perspective must be either 'client' or 'server'")

        self.app = app
        self.title = title
        self.version = version
        self.description = description
        self.servers = copy.deepcopy(dict(servers)) if servers is not None else None
        self.perspective = perspective
        self._mounted_paths: set[str] = set()
        self._mounted_yaml_paths: set[str] = set()

    def generate(self) -> dict[str, Any]:
        """Build and return a fresh AsyncAPI document dictionary."""

        document: dict[str, Any] = {
            "asyncapi": _ASYNCAPI_VERSION,
            "info": {
                "title": self.title,
                "version": self.version,
            },
            "defaultContentType": _JSON_CONTENT_TYPE,
            "channels": {},
            "operations": {},
            "components": {
                "schemas": {},
                "messages": {},
            },
        }
        if self.description is not None:
            document["info"]["description"] = self.description
        if self.servers is not None:
            document["servers"] = copy.deepcopy(self.servers)

        context = _GenerationContext(document, perspective=self.perspective)
        for route in iter_websocket_routes(self.app.routes):
            context.add_route(route)
        return document

    def mount(self, path: str = "/asyncapi.json", *, name: str = "asyncapi") -> None:
        """Mount a JSON document endpoint on the FastAPI application."""

        _validate_mount_arguments(path, name)
        if path in self._mounted_yaml_paths:
            raise ValueError(f"path is already mounted as YAML: {path!r}")
        if path in self._mounted_paths:
            return

        async def asyncapi_json() -> dict[str, Any]:
            return self.generate()

        self.app.add_api_route(
            path,
            asyncapi_json,
            methods=["GET"],
            name=name,
            include_in_schema=False,
            response_class=JSONResponse,
        )
        self._mounted_paths.add(path)

    def mount_yaml(
        self,
        path: str = "/asyncapi.yaml",
        *,
        name: str = "asyncapi_yaml",
    ) -> None:
        """Mount a YAML document endpoint using the optional YAML extra."""

        _validate_mount_arguments(path, name)
        self._get_yaml_module()
        if path in self._mounted_paths:
            raise ValueError(f"path is already mounted as JSON: {path!r}")
        if path in self._mounted_yaml_paths:
            return

        async def asyncapi_yaml() -> PlainTextResponse:
            return PlainTextResponse(
                content=self.to_yaml(),
                media_type="application/yaml",
            )

        self.app.add_api_route(
            path,
            asyncapi_yaml,
            methods=["GET"],
            name=name,
            include_in_schema=False,
            response_class=PlainTextResponse,
        )
        self._mounted_yaml_paths.add(path)

    def to_yaml(self, *, sort_keys: bool = False) -> str:
        """Serialize the generated document as YAML using the optional extra."""

        yaml = self._get_yaml_module()
        return yaml.safe_dump(
            self.generate(),
            allow_unicode=True,
            sort_keys=sort_keys,
        )

    @staticmethod
    def _get_yaml_module() -> Any:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on installation
            raise MissingYamlDependencyError(
                "YAML support requires the optional dependency; install "
                "fast-asyncapidoc[yaml]"
            ) from exc
        return yaml


class _GenerationContext:
    def __init__(
        self,
        document: dict[str, Any],
        *,
        perspective: Perspective,
    ) -> None:
        self.document = document
        self.perspective = perspective
        self.channels: dict[str, Any] = document["channels"]
        self.operations: dict[str, Any] = document["operations"]
        self.schemas: dict[str, Any] = document["components"]["schemas"]
        self.messages: dict[str, Any] = document["components"]["messages"]
        self.schema_keys_by_model: dict[type[Any], str] = {}
        self.message_keys: dict[tuple[str, str, str], str] = {}

    def add_route(self, route: WebSocketRouteInfo) -> None:
        specs = get_operation_specs(route.endpoint)
        if not specs:
            return

        channel_id = self._channel_id(route.path)
        channel = self.channels.setdefault(
            channel_id,
            self._new_channel(route.path),
        )
        if channel["address"] != route.path:
            channel_id = self._unique_key(channel_id, route.path, self.channels)
            channel = self.channels.setdefault(
                channel_id,
                self._new_channel(route.path),
            )
        self._apply_channel_spec(channel, get_channel_spec(route.endpoint))
        security_refs = self._register_security(route.endpoint)

        for index, spec in enumerate(specs):
            operation_id = self._operation_id(route, spec, index)
            has_inputs = bool(spec.inputs)
            has_outputs = bool(spec.outputs)
            operation: dict[str, Any] = {
                "action": self._operation_action(spec, has_inputs),
                "channel": {"$ref": f"#/channels/{channel_id}"},
                "messages": [],
            }
            if security_refs:
                operation["security"] = copy.deepcopy(security_refs)
            self._add_operation_metadata(operation, spec)

            if has_inputs:
                input_refs = [
                    self._register_message(
                        channel=channel,
                        channel_id=channel_id,
                        direction="input",
                        model=model,
                    )
                    for model in spec.inputs
                ]
                operation["messages"] = self._message_refs(channel_id, input_refs)

            if has_inputs and has_outputs:
                output_ids = [
                    self._register_message(
                        channel=channel,
                        channel_id=channel_id,
                        direction="output",
                        model=model,
                    )
                    for model in spec.outputs
                ]
                operation["reply"] = {
                    "channel": {"$ref": f"#/channels/{channel_id}"},
                    "messages": self._message_refs(channel_id, output_ids),
                }
            elif has_outputs:
                output_ids = [
                    self._register_message(
                        channel=channel,
                        channel_id=channel_id,
                        direction="output",
                        model=model,
                    )
                    for model in spec.outputs
                ]
                operation["messages"] = self._message_refs(channel_id, output_ids)

            self.operations[operation_id] = operation

    @staticmethod
    def _new_channel(path: str) -> dict[str, Any]:
        return {
            "address": path,
            "bindings": {"ws": {"bindingVersion": _WEBSOCKET_BINDING_VERSION}},
            "messages": {},
        }

    def _apply_channel_spec(
        self,
        channel: dict[str, Any],
        spec: Any,
    ) -> None:
        if spec is None:
            return
        metadata = spec.to_document()
        for key, value in metadata.items():
            if key in {"address", "messages"}:
                raise InvalidAsyncAPIChannelError(
                    f"channel metadata cannot override generated field: {key}"
                )
            if key == "bindings":
                bindings = channel.setdefault("bindings", {})
                for binding_name, binding in value.items():
                    if (
                        binding_name == "ws"
                        and isinstance(binding, Mapping)
                        and isinstance(bindings.get("ws"), Mapping)
                    ):
                        bindings["ws"] = {
                            **bindings["ws"],
                            **copy.deepcopy(dict(binding)),
                        }
                    else:
                        bindings[binding_name] = copy.deepcopy(binding)
                continue
            existing = channel.get(key)
            if existing is not None and existing != value:
                raise InvalidAsyncAPIChannelError(
                    f"conflicting channel metadata for {key!r}"
                )
            channel[key] = copy.deepcopy(value)

    def _register_security(self, endpoint: Any) -> list[dict[str, str]]:
        declarations = get_security_schemes(endpoint)
        if not declarations:
            return []

        components = self.document["components"]
        schemes = components.setdefault("securitySchemes", {})
        references: list[dict[str, str]] = []
        for scheme_id, scheme in declarations:
            existing = schemes.get(scheme_id)
            if existing is not None and existing != scheme:
                raise DuplicateSecuritySchemeError(
                    f"conflicting security scheme: {scheme_id!r}"
                )
            schemes[scheme_id] = copy.deepcopy(scheme)
            reference = {"$ref": f"#/components/securitySchemes/{scheme_id}"}
            if reference not in references:
                references.append(reference)
        return references

    def _operation_action(self, spec: OperationSpec, has_inputs: bool) -> str:
        if spec.action is not None:
            return spec.action
        if self.perspective == "client":
            return "send" if has_inputs else "receive"
        return "receive" if has_inputs else "send"

    @staticmethod
    def _message_refs(channel_id: str, message_ids: list[str]) -> list[dict[str, str]]:
        return [
            {"$ref": f"#/channels/{channel_id}/messages/{message_id}"}
            for message_id in message_ids
        ]

    def _operation_id(
        self, route: WebSocketRouteInfo, spec: OperationSpec, index: int
    ) -> str:
        if spec.operation_id is not None:
            if spec.operation_id in self.operations:
                raise DuplicateOperationIdError(
                    f"duplicate operation_id: {spec.operation_id!r}"
                )
            return spec.operation_id

        endpoint_name = getattr(route.endpoint, "__name__", None)
        base = route.name or endpoint_name or "websocket"
        if len(get_operation_specs(route.endpoint)) > 1:
            base = f"{base}__{index + 1}"
        return self._unique_key(base, f"{route.path}:{index}", self.operations)

    def _add_operation_metadata(
        self, operation: dict[str, Any], spec: OperationSpec
    ) -> None:
        if spec.action is not None:
            operation["action"] = spec.action
        if spec.title is not None:
            operation["title"] = spec.title
        if spec.summary is not None:
            operation["summary"] = spec.summary
        if spec.description is not None:
            operation["description"] = spec.description
        if spec.tags:
            operation["tags"] = [{"name": tag} for tag in spec.tags]

    def _register_message(
        self,
        *,
        channel: dict[str, Any],
        channel_id: str,
        direction: str,
        model: type[Any],
    ) -> str:
        schema_key = self._register_model_schema(model)
        message_key = (channel_id, direction, schema_key)
        message_id = self.message_keys.get(message_key)
        if message_id is None:
            base_message_id = _safe_key(f"{channel_id}_{direction}_{schema_key}")
            message_id = self._unique_key(
                base_message_id,
                f"{channel_id}:{direction}:{schema_key}",
                self.messages,
            )
            self.message_keys[message_key] = message_id

        if message_id not in self.messages:
            schema = self.schemas[schema_key]
            message: dict[str, Any] = {
                "name": message_id,
                "contentType": _JSON_CONTENT_TYPE,
                "payload": {"$ref": f"#/components/schemas/{schema_key}"},
            }
            if isinstance(schema.get("title"), str):
                message["title"] = schema["title"]
            if isinstance(schema.get("description"), str):
                message["description"] = schema["description"]
            message_spec = get_message_spec(model)
            if message_spec is not None:
                message.update(message_spec.to_document())
            self.messages[message_id] = message

        channel["messages"][message_id] = {
            "$ref": f"#/components/messages/{message_id}"
        }
        return message_id

    def _register_model_schema(self, model: type[Any]) -> str:
        existing_key = self.schema_keys_by_model.get(model)
        if existing_key is not None:
            return existing_key

        raw_schema = copy.deepcopy(
            model.model_json_schema(ref_template="#/components/schemas/{model}")
        )
        definitions = raw_schema.pop("$defs", {})
        local_keys: dict[str, str] = {}
        for name, schema in definitions.items():
            local_keys[name] = self._schema_key(name, schema)
        root_key = self._schema_key(model.__name__, raw_schema)
        self.schema_keys_by_model[model] = root_key

        for name, schema in definitions.items():
            key = local_keys[name]
            rewritten = _rewrite_schema_refs(schema, local_keys)
            if key not in self.schemas:
                self.schemas[key] = rewritten
        self.schemas[root_key] = _rewrite_schema_refs(raw_schema, local_keys)
        return root_key

    def _schema_key(self, name: str, schema: Any) -> str:
        base = _safe_key(name) or "Model"
        return self._unique_key(base, json.dumps(schema, sort_keys=True), self.schemas)

    @staticmethod
    def _channel_id(path: str) -> str:
        stripped = path.strip("/")
        if not stripped:
            return "root"
        return _safe_key(stripped.replace("/", "_")) or "channel"

    @staticmethod
    def _unique_key(base: str, identity: str, existing: Mapping[str, Any]) -> str:
        if base not in existing:
            return base
        if identity == base:
            return base
        digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8]
        candidate = f"{base}__{digest}"
        counter = 2
        while candidate in existing:
            candidate = f"{base}__{digest}_{counter}"
            counter += 1
        return candidate


def _validate_mount_arguments(path: str, name: str) -> None:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("path must be an absolute route path")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")


def _safe_key(value: str) -> str:
    value = _KEY_PATTERN.sub("_", value).strip("._-")
    return value or "item"


def _rewrite_schema_refs(value: Any, local_keys: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                if child.startswith("#/$defs/"):
                    name = child.removeprefix("#/$defs/")
                    child = f"#/components/schemas/{local_keys.get(name, name)}"
                elif child.startswith("#/components/schemas/"):
                    name = child.removeprefix("#/components/schemas/")
                    child = f"#/components/schemas/{local_keys.get(name, name)}"
            rewritten[key] = _rewrite_schema_refs(child, local_keys)
        return rewritten
    if isinstance(value, list):
        return [_rewrite_schema_refs(item, local_keys) for item in value]
    return value
