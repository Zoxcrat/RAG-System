#!/usr/bin/env sh
set -e

# Both steps are safe to run on every boot: the schema uses CREATE ... IF NOT
# EXISTS and ingestion is idempotent (ON CONFLICT DO NOTHING).

echo "[entrypoint] Initializing schema..."
python -m src.db

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your_key_here" ]; then
  echo "[entrypoint] OPENAI_API_KEY is not set; skipping ingestion."
  echo "[entrypoint] Put a real key in .env to embed data/sample_docs.txt."
else
  echo "[entrypoint] Ingesting sample docs (idempotent)..."
  python -m src.ingestion.ingest || echo "[entrypoint] Ingestion failed; continuing."
fi

# Run whatever command was passed (defaults to the interactive CLI).
exec "$@"
