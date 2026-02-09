#!/bin/bash
# Generate TypeScript types from backend OpenAPI schema.
# Run this after backend schema changes to keep frontend types in sync.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Exporting OpenAPI schema..."
uv run python "$SCRIPT_DIR/export-openapi.py" "$PROJECT_ROOT/frontend/src/types/generated/openapi.json"

echo "Generating TypeScript types..."
cd "$PROJECT_ROOT/frontend" && pnpm generate:types

echo "Done! Generated types are in frontend/src/types/generated/"
