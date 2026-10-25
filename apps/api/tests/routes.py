"""Every API route of an app, with its dependencies, for tests that walk the routes.

Since FastAPI 0.162, `app.routes` holds included routers rather than their routes: walking it
for `APIRoute` finds nothing, and a test built that way passes without checking anything.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute


@dataclass(frozen=True, slots=True)
class ApiRoute:
    method: str
    path: str
    operation_id: str | None
    include_in_schema: bool
    dependant: Dependant

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    def depends_on(self, call: Callable[..., Any]) -> bool:
        return _depends_on(self.dependant, call)


def _depends_on(dependant: Dependant, call: Callable[..., Any]) -> bool:
    return any(sub.call is call or _depends_on(sub, call) for sub in dependant.dependencies)


def api_routes(app: FastAPI) -> list[ApiRoute]:
    routes = list(_walk(app))
    assert routes, "no route found: the way FastAPI exposes routes has changed"
    return routes


def _walk(app: FastAPI) -> Iterator[ApiRoute]:
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        found: list[Any] = list(contexts()) if contexts else []
        if isinstance(route, APIRoute):
            found.append(route)
        for context in found:
            for method in sorted(context.methods):
                yield ApiRoute(
                    method=method,
                    path=context.path,
                    operation_id=context.operation_id,
                    include_in_schema=context.include_in_schema,
                    dependant=context.dependant,
                )
