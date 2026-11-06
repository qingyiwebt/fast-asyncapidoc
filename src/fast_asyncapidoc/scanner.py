"""FastAPI/Starlette WebSocket route discovery."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi.routing import APIWebSocketRoute
from starlette.routing import Mount, WebSocketRoute


@dataclass(frozen=True)
class WebSocketRouteInfo:
    """The route information needed by the document generator."""

    path: str
    endpoint: Any
    name: str | None


_WEBSOCKET_ROUTE_TYPES = (APIWebSocketRoute, WebSocketRoute)


def iter_websocket_routes(routes: Iterable[Any]) -> Iterator[WebSocketRouteInfo]:
    """Yield WebSocket routes with their effective mounted paths.

    FastAPI releases that use lazy router inclusion expose an internal
    ``_IncludedRouter`` object rather than flattening routes into
    ``app.routes``.  Its capability-based ``effective_route_contexts`` method
    gives us the final Starlette route and therefore preserves include
    prefixes.  Older FastAPI releases continue to work through the direct
    route and Mount branches below.
    """

    for route in routes:
        if isinstance(route, _WEBSOCKET_ROUTE_TYPES):
            yield _route_info(route)
            continue

        effective_contexts = getattr(route, "effective_route_contexts", None)
        if callable(effective_contexts):
            for context in effective_contexts():
                effective_route = getattr(context, "starlette_route", None)
                original_route = getattr(context, "original_route", None)
                if isinstance(effective_route, _WEBSOCKET_ROUTE_TYPES):
                    yield _route_info(
                        effective_route,
                        endpoint=getattr(original_route, "endpoint", None),
                    )
                else:
                    nested_routes = getattr(effective_route, "routes", None)
                    if nested_routes is not None:
                        yield from iter_websocket_routes(nested_routes)
            continue

        if isinstance(route, Mount):
            nested_routes = getattr(route, "routes", None)
            if nested_routes is not None:
                prefix = getattr(route, "path", "")
                yield from _with_prefix(iter_websocket_routes(nested_routes), prefix)
            continue

        nested_routes = getattr(route, "routes", None)
        if nested_routes is not None:
            yield from iter_websocket_routes(nested_routes)


def _route_info(route: Any, *, endpoint: Any | None = None) -> WebSocketRouteInfo:
    actual_endpoint = (
        endpoint if endpoint is not None else getattr(route, "endpoint", None)
    )
    return WebSocketRouteInfo(
        path=getattr(route, "path", "/") or "/",
        endpoint=actual_endpoint,
        name=getattr(route, "name", None),
    )


def _with_prefix(
    routes: Iterable[WebSocketRouteInfo], prefix: str
) -> Iterator[WebSocketRouteInfo]:
    for route in routes:
        yield WebSocketRouteInfo(
            path=join_paths(prefix, route.path),
            endpoint=route.endpoint,
            name=route.name,
        )


def join_paths(prefix: str, path: str) -> str:
    """Join mounted paths while preserving a route's trailing slash."""

    prefix = prefix or ""
    path = path or "/"
    if not prefix or prefix == "/":
        return path if path.startswith("/") else f"/{path}"
    if path == "/":
        return prefix if prefix.startswith("/") else f"/{prefix}"

    result = f"/{prefix.strip('/')}/{path.strip('/')}"
    if path.endswith("/") and not result.endswith("/"):
        result += "/"
    return result
