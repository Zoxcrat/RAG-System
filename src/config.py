"""Configuration loaded from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


# --- Database (defaults match docker-compose) ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _get_int("DB_PORT", 5432)
DB_NAME = os.getenv("DB_NAME", "rag_db")
DB_USER = os.getenv("DB_USER", "rag_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "rag_password")

# --- OpenAI client ---
OPENAI_MAX_RETRIES = _get_int("OPENAI_MAX_RETRIES", 3)
OPENAI_TIMEOUT = _get_float("OPENAI_TIMEOUT", 30.0)

# --- Embeddings ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = _get_int("EMBEDDING_DIM", 1536)
# Stays under the OpenAI embeddings limit of 2048 inputs per request.
EMBED_BATCH_SIZE = _get_int("EMBED_BATCH_SIZE", 1000)

# --- Query expansion (multi-query / RAG-Fusion) ---
# Off by default: it hurt recall@5 (0.91 -> 0.82) on the eval set. See docs/16-query-expansion-evaluado.md.
QUERY_EXPANSION_ENABLED = os.getenv("QUERY_EXPANSION_ENABLED", "false").lower() in ("1", "true", "yes")
QUERY_EXPANSION_N = _get_int("QUERY_EXPANSION_N", 3)  # total queries incl. the original

# --- Retrieval (hybrid search) ---
# Candidates per arm before fusing; kept larger than top_k so one arm can rescue the other.
RETRIEVAL_CANDIDATES = _get_int("RETRIEVAL_CANDIDATES", 20)
# RRF constant; 60 is the value from the original RRF paper.
RRF_K = _get_int("RRF_K", 60)

# --- Aggregation (structured parts table + text-to-SQL) ---
# Route count/list/group questions to SQL over the parts table instead of top-k retrieval.
AGG_ENABLED = os.getenv("AGG_ENABLED", "true").lower() in ("1", "true", "yes")
# Cap rows fed to the model when formatting the answer.
AGG_ROW_LIMIT = _get_int("AGG_ROW_LIMIT", 200)
# Sample this many SQL candidates and take the majority result (1 = no voting). Needs temperature > 0.
AGG_SELF_CONSISTENCY = _get_int("AGG_SELF_CONSISTENCY", 3)
AGG_SAMPLE_TEMPERATURE = _get_float("AGG_SAMPLE_TEMPERATURE", 0.4)
# Aggregation (text-to-SQL + answer) uses a stronger model than the rest: the
# census-vs-variety reasoning and structural breakdowns (ribs by sub-type/side)
# need it. Few, small calls, so the cost is negligible.
AGG_MODEL = os.getenv("AGG_MODEL", "gpt-4o")

# --- Reranking ---
# LLM reranker reorders the candidates after hybrid retrieval; disable to keep the fused order.
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
RERANK_CANDIDATES = _get_int("RERANK_CANDIDATES", 20)

# --- Generation / RAG ---
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# Reranker reuses the chat model by default.
RERANK_MODEL = os.getenv("RERANK_MODEL", LLM_MODEL)
# Chunks fed to the LLM. 10 (not 5) so the keyword arm's rescued hits reach the context.
DEFAULT_TOP_K = _get_int("DEFAULT_TOP_K", 10)
TEMPERATURE = _get_float("TEMPERATURE", 0.0)
MAX_TOKENS = _get_int("MAX_TOKENS", 800)
RELEVANCE_THRESHOLD = _get_float("RELEVANCE_THRESHOLD", 0.5)

# --- Ingestion ---
CHUNK_SIZE = _get_int("CHUNK_SIZE", 500)
CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 100)

# --- API ---
# PDF served to the frontend viewer (GET /pdf).
PDF_PATH = os.getenv("PDF_PATH", "data/Cessna 172 Parts Catalog (1963-1974).pdf")
# Comma-separated allowed CORS origins.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
