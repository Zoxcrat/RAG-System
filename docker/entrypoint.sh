#!/usr/bin/env sh
set -e

# Schema init is safe on every boot (CREATE ... IF NOT EXISTS). Data ingestion is
# a separate, explicit step (it embeds ~14k chunks and costs money), not run here.
echo "[entrypoint] Initializing schema..."
python -m src.db

exec "$@"
