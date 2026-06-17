"""Centralized configuration.

Single place that reads environment variables, so the rest of the code never
touches os.getenv directly. Deliberately dependency-free (no pydantic) to keep
every value easy to trace. load_dotenv() runs once, here.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


# --- Database (defaults match docker-compose, so the app connects out of the box) ---
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
# OpenAI's embeddings endpoint rejects requests with more than 2048 inputs (and
# also caps total tokens per request), so embed_texts splits large inputs into
# batches of this size. 1000 stays well under both limits for our ~500-char chunks.
EMBED_BATCH_SIZE = _get_int("EMBED_BATCH_SIZE", 1000)

# --- Retrieval (hybrid search) ---
# Each arm (vector + keyword) pulls this many candidates before fusing. Larger
# than top_k so a chunk ranked outside the final top_k by one arm can still be
# rescued by the other (this is what fixes buried-fact recall).
RETRIEVAL_CANDIDATES = _get_int("RETRIEVAL_CANDIDATES", 20)
# Reciprocal Rank Fusion constant: score = sum(1 / (RRF_K + rank)). 60 is the
# value from the original RRF paper; it dampens the top ranks so lower-ranked
# results still contribute and one arm can't fully dominate.
RRF_K = _get_int("RRF_K", 60)

# --- Reranking ---
# After hybrid retrieval, an LLM reranker reorders the candidates by relevance
# (a cross-encoder-style step). It runs on this many candidates and narrows them
# to DEFAULT_TOP_K for the prompt. Disable to fall back to the fused order.
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
RERANK_CANDIDATES = _get_int("RERANK_CANDIDATES", 20)

# --- Generation / RAG ---
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# Reranker model: reuse the cheap chat model by default (no extra dependency).
RERANK_MODEL = os.getenv("RERANK_MODEL", LLM_MODEL)
# Chunks fed to the LLM. Bumped 5 -> 10 alongside hybrid search: dense catalog
# tables share generic words ("part", "number", "hanger"), so a buried fact can
# sit a few ranks deep after fusion; a deeper window lets the keyword arm's rescue
# actually reach the context. Cost is still a fraction of a cent with gpt-4o-mini.
DEFAULT_TOP_K = _get_int("DEFAULT_TOP_K", 10)
TEMPERATURE = _get_float("TEMPERATURE", 0.0)
MAX_TOKENS = _get_int("MAX_TOKENS", 800)
RELEVANCE_THRESHOLD = _get_float("RELEVANCE_THRESHOLD", 0.5)

# --- Ingestion ---
CHUNK_SIZE = _get_int("CHUNK_SIZE", 500)
CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 100)

# --- API ---
# Path to the PDF served to the frontend viewer (GET /pdf).
PDF_PATH = os.getenv("PDF_PATH", "data/Cessna 172 Parts Catalog (1963-1974).pdf")
# Comma-separated allowed CORS origins; "*" (default) is fine for local dev.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
