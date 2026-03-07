"""Export OpenAPI schema from FastAPI app without starting the server.

Usage:
    uv run python scripts/export-openapi.py [output_path]

This works by calling create_app() which registers routes and middleware
but does NOT trigger the lifespan (no DB/Redis connection needed).
Dummy env vars are set for Settings validation if not already configured.
"""

import json
import os
import sys

# Set dummy env vars for Settings validation (only if not already set)
_DUMMY_VARS = {
    "DATABASE_URL": "postgresql+asyncpg://dummy:dummy@localhost:5432/dummy",
    "REDIS_URL": "redis://localhost:6379",
    "SECRET_KEY": "dummy-secret-key-for-schema-export-only-min-32",
    "ENCRYPTION_KEY": "dummy-encryption-key-for-schema-export-only!",
}
for key, value in _DUMMY_VARS.items():
    os.environ.setdefault(key, value)

# Clear lru_cache in case settings were already loaded
from squant.config import get_settings  # noqa: E402

get_settings.cache_clear()

from squant.main import create_app  # noqa: E402

app = create_app()
schema = app.openapi()

output_path = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"

# Ensure output directory exists
os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

with open(output_path, "w") as f:
    json.dump(schema, f, indent=2, ensure_ascii=False)

print(f"OpenAPI schema exported to {output_path} ({len(schema.get('paths', {}))} paths)")
