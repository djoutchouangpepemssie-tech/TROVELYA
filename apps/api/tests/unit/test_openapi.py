"""The OpenAPI contract (section 11.6): stable, explicit operation ids for the generated client."""

import json
import subprocess
import sys
from pathlib import Path

from fastapi.routing import APIRoute

from tests.conftest import make_settings
from trovelya.main import create_app
from trovelya.scripts.export_openapi import export_openapi


def test_all_routes_have_explicit_operation_id() -> None:
    app = create_app(make_settings(env="production"))
    missing = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.include_in_schema and not route.operation_id
    ]
    assert missing == []


def test_operation_ids_are_unique() -> None:
    schema = create_app(make_settings(env="production")).openapi()
    ids = [op["operationId"] for path in schema["paths"].values() for op in path.values()]
    assert len(ids) == len(set(ids))


def test_export_is_deterministic_and_excludes_test_routes(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    export_openapi(first)
    export_openapi(second)
    assert first.read_bytes() == second.read_bytes()
    schema = json.loads(first.read_text())
    assert schema["info"]["title"] == "TROVÉLYA API"
    assert "/health" in schema["paths"]
    assert not [p for p in schema["paths"] if p.startswith("/v1/_test")]


def test_export_runs_without_environment(tmp_path: Path) -> None:
    """CI and developers generate the contract without any secret or database."""
    out = tmp_path / "openapi.json"
    result = subprocess.run(  # noqa: S603 — fixed interpreter and module
        [sys.executable, "-m", "trovelya.scripts.export_openapi", str(out)],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(out.read_text())["openapi"].startswith("3.1")
