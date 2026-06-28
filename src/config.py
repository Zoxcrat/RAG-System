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
# Connection pool for the API; scripts/CLI use a single direct connection.
DB_POOL_MIN = _get_int("DB_POOL_MIN", 1)
DB_POOL_MAX = _get_int("DB_POOL_MAX", 10)

# --- OpenAI client ---
OPENAI_MAX_RETRIES = _get_int("OPENAI_MAX_RETRIES", 3)
OPENAI_TIMEOUT = _get_float("OPENAI_TIMEOUT", 30.0)

# --- Embeddings ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = _get_int("EMBEDDING_DIM", 1536)
# Under the OpenAI limit of 2048 inputs per request.
EMBED_BATCH_SIZE = _get_int("EMBED_BATCH_SIZE", 1000)

# --- Retrieval (hybrid search) ---
# Candidates per arm before fusing; larger than top_k so one arm can rescue the other.
RETRIEVAL_CANDIDATES = _get_int("RETRIEVAL_CANDIDATES", 20)
# RRF constant from the original paper.
RRF_K = _get_int("RRF_K", 60)

# --- Aggregation (structured parts table + text-to-SQL) ---
# Route count/list/group questions to SQL over the parts table instead of top-k retrieval.
AGG_ENABLED = os.getenv("AGG_ENABLED", "true").lower() in ("1", "true", "yes")
# Cap rows fed to the model when formatting the answer.
AGG_ROW_LIMIT = _get_int("AGG_ROW_LIMIT", 200)
# SQL candidates to sample and majority-vote over (1 = off); needs temperature > 0.
AGG_SELF_CONSISTENCY = _get_int("AGG_SELF_CONSISTENCY", 3)
AGG_SAMPLE_TEMPERATURE = _get_float("AGG_SAMPLE_TEMPERATURE", 0.4)
# Stronger model for the SQL reasoning; few small calls, so cost is negligible.
AGG_MODEL = os.getenv("AGG_MODEL", "gpt-4o")

# --- Reranking ---
# LLM reranks candidates after hybrid retrieval; disable to keep the fused order.
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
RERANK_CANDIDATES = _get_int("RERANK_CANDIDATES", 20)

# --- Generation / RAG ---
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# Reranker reuses the chat model by default.
RERANK_MODEL = os.getenv("RERANK_MODEL", LLM_MODEL)
# Chunks fed to the LLM; 10 so the keyword arm's rescued hits reach the context.
DEFAULT_TOP_K = _get_int("DEFAULT_TOP_K", 10)
TEMPERATURE = _get_float("TEMPERATURE", 0.0)
MAX_TOKENS = _get_int("MAX_TOKENS", 800)
# Cosine distance above which the semantic path refuses (out-of-domain gate).
# Eval set: in-domain tops out ~0.59, out-of-domain starts ~0.74, so 0.65 sits in the gap. See docs/24.
RELEVANCE_THRESHOLD = _get_float("RELEVANCE_THRESHOLD", 0.65)

# --- Ingestion ---
CHUNK_SIZE = _get_int("CHUNK_SIZE", 500)
CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 100)

# --- API ---
# PDF served to the frontend viewer (GET /pdf).
PDF_PATH = os.getenv("PDF_PATH", "data/Cessna 172 Parts Catalog (1963-1974).pdf")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
