"""Write the API contract to a file (section 11.6).

Run: python -m trovelya.scripts.export_openapi <path>

The schema depends only on the code: placeholder settings are used so no secret, database
or Redis is needed. Production settings are used so test-only routes are excluded.
"""

import json
import sys
from pathlib import Path

from pydantic import SecretStr

from trovelya.core.config import Settings
from trovelya.main import create_app

_PLACEHOLDER_SETTINGS = Settings(
    env="production",
    database_url="postgresql+asyncpg://contract:contract@localhost/contract",
    redis_url="redis://localhost:6379/0",
    secret_key=SecretStr("contract-export-only-" + "x" * 64),
    proxy_shared_secret=SecretStr("contract-export-only-" + "y" * 32),
    field_encryption_key=SecretStr("contract-export-only-" + "z" * 32),
    web_origin="https://trovelya.com",
    admin_origin="https://admin.trovelya.com",
)


def export_openapi(path: Path) -> None:
    schema = create_app(_PLACEHOLDER_SETTINGS).openapi()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    export_openapi(Path(sys.argv[1]))
