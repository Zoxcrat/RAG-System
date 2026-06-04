import psycopg2

from src import config

EMBEDDING_DIM = config.EMBEDDING_DIM


def get_connection():
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


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
                content_hash TEXT,
                embedding vector({EMBEDDING_DIM}),
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        # Backward-compatible migration for tables created before content_hash existed.
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;")
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_embedding_hnsw_idx
            ON documents
            USING hnsw (embedding vector_cosine_ops);
            """
        )
        # Dedup key: the same chunk text is never stored twice, which makes
        # re-running ingestion idempotent (paired with ON CONFLICT in ingest.py).
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS documents_content_hash_uidx
            ON documents (content_hash);
            """
        )
    conn.commit()


def reset_db(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS documents;")
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
