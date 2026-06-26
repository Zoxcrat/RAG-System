from typing import Optional

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

from src import config

EMBEDDING_DIM = config.EMBEDDING_DIM


def _conn_kwargs() -> dict:
    return {
        "host": config.DB_HOST,
        "port": config.DB_PORT,
        "dbname": config.DB_NAME,
        "user": config.DB_USER,
        "password": config.DB_PASSWORD,
    }


def get_connection():
    """A single direct connection. Used by scripts, ingestion, the CLI and eval."""
    return psycopg2.connect(**_conn_kwargs())


_pool: Optional[ThreadedConnectionPool] = None


def get_pool() -> ThreadedConnectionPool:
    """Lazily-built connection pool for the API.

    FastAPI serves sync endpoints from a thread pool, so a thread-safe pool lets
    concurrent requests reuse a bounded set of connections instead of opening one
    per request (which storms Postgres and exhausts its connection slots).
    """
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            config.DB_POOL_MIN, config.DB_POOL_MAX, **_conn_kwargs()
        )
    return _pool


def close_pool() -> None:
    """Close all pooled connections on shutdown. No-op if the pool was never built."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def init_schema(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT,
                chunk_index INTEGER,
                page_number INTEGER,
                content_hash TEXT,
                embedding vector({EMBEDDING_DIM}),
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        # Migrations for columns added after the table first shipped.
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_number INTEGER;")
        # Full-text vector for hybrid retrieval. Strip OCR noise chars (~ = | `) first:
        # left in, they corrupt tokenization ('~headliner' never matches 'headliner').
        # Hyphens are kept so part numbers like 0512029-8 index both whole and split.
        cur.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS "
            "(to_tsvector('english', regexp_replace(content, '[~=|`]+', ' ', 'g'))) "
            "STORED;"
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_embedding_hnsw_idx
            ON documents
            USING hnsw (embedding vector_cosine_ops);
            """
        )
        # GIN index for fast @@ full-text matching.
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_tsv_gin_idx
            ON documents USING GIN (tsv);
            """
        )
        # Dedup key making re-ingestion idempotent (paired with ON CONFLICT in ingest.py).
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS documents_content_hash_uidx
            ON documents (content_hash);
            """
        )
        # Structured parts table for aggregation queries. One row per catalog part
        # line. Built from vision-LLM page extraction (see src/ingestion/vision_parts.py),
        # which recovers the columns flat OCR destroys (units, usable-on, station).
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS parts (
                id SERIAL PRIMARY KEY,
                part_number TEXT,
                description TEXT,
                page_number INTEGER,
                figure TEXT
            );
            """
        )
        # Schema v2 columns (the structural signals flat OCR loses). Added to
        # pre-existing tables idempotently, same policy as the documents table.
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS units_per_assy INTEGER;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS usable_on TEXT;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS station TEXT;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS index_no TEXT;")
    conn.commit()


def reset_db(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS documents;")
        cur.execute("DROP TABLE IF EXISTS parts;")
    conn.commit()
    init_schema(conn)


if __name__ == "__main__":
    try:
        with get_connection() as conn:
            init_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        print("Schema initialized successfully")
    except Exception as e:
        print(f"Error: {e}")
