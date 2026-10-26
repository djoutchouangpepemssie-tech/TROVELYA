"""A real Garage node (S3-compatible, ADR-0019) for the storage tests, one per test session."""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from testcontainers.core.container import DockerContainer

from trovelya.modules.media.adapters.storage import Bucket, S3Storage

GARAGE_IMAGE = "dxflrs/garage:v2.1.0"
CONFIG = Path(__file__).resolve().parents[5] / "infra" / "garage" / "garage.toml"
BUCKETS: dict[Bucket, str] = {"originals": "test-originals", "variants": "test-variants"}


def _garage(container: DockerContainer, *args: str) -> str:
    code, output = container.exec(["/garage", *args])
    text = bytes(output).decode()  # pyright: ignore[reportArgumentType]
    assert code == 0, text
    return text


@pytest.fixture(scope="session")
def garage() -> Iterator[S3Storage]:
    container = (
        DockerContainer(GARAGE_IMAGE)
        .with_volume_mapping(str(CONFIG), "/etc/garage.toml", "ro")
        .with_exposed_ports(3900)
    )
    with container:
        for _ in range(60):
            if container.exec(["/garage", "status"])[0] == 0:
                break
            time.sleep(0.5)
        node = _garage(container, "node", "id", "-q").strip().split("@")[0]
        _garage(container, "layout", "assign", "-z", "test", "-c", "1G", node)
        _garage(container, "layout", "apply", "--version", "1")
        key = _garage(container, "key", "create", "test-key")
        key_id = next(line.split()[-1] for line in key.splitlines() if "Key ID" in line)
        secret = next(line.split()[-1] for line in key.splitlines() if "Secret key" in line)
        for name in BUCKETS.values():
            _garage(container, "bucket", "create", name)
            _garage(
                container,
                "bucket",
                "allow",
                "--read",
                "--write",
                "--owner",
                name,
                "--key",
                "test-key",
            )
        host = container.get_container_host_ip()
        port = container.get_exposed_port(3900)
        yield S3Storage(
            endpoint_url=f"http://{host}:{port}",
            region="garage",
            access_key_id=key_id,
            secret_access_key=secret,
            buckets=BUCKETS,
        )
