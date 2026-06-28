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
    """Lazily-built thread-safe connection pool for the API."""
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            config.DB_POOL_MIN, config.DB_POOL_MAX, **_conn_kwargs()
        )
    return _pool


def close_pool() -> None:
    """Close all pooled connections on shutdown."""
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
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_number INTEGER;")
        # Strip OCR noise chars (~ = | `) before tokenizing; keep hyphens so part numbers index whole and split.
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
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_tsv_gin_idx
            ON documents USING GIN (tsv);
            """
        )
        # Dedup key for idempotent re-ingestion (paired with ON CONFLICT in ingest.py).
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS documents_content_hash_uidx
            ON documents (content_hash);
            """
        )
        # Structured parts table for aggregation queries; one row per catalog part line.
        # Built from vision-LLM extraction (src/ingestion/vision_parts.py).
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
        # Schema v2 columns: structural signals flat OCR loses.
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS units_per_assy INTEGER;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS usable_on TEXT;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS station TEXT;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS index_no TEXT;")
        # Schema v3: typed columns derived once at ingest (src/ingestion/normalize.py) so
        # aggregation groups on them instead of re-deriving with ILIKE. variant separates
        # standard wing from long-range (mixing them caused the rib over-count).
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS station_num DOUBLE PRECISION;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS side TEXT;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS part_category TEXT;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS sub_type TEXT;")
        cur.execute("ALTER TABLE parts ADD COLUMN IF NOT EXISTS variant TEXT;")
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
