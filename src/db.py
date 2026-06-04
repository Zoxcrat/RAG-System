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
                embedding vector({EMBEDDING_DIM}),
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_embedding_hnsw_idx
            ON documents
            USING hnsw (embedding vector_cosine_ops);
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
