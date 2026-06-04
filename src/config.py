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

# --- Generation / RAG ---
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
DEFAULT_TOP_K = _get_int("DEFAULT_TOP_K", 5)
TEMPERATURE = _get_float("TEMPERATURE", 0.0)
MAX_TOKENS = _get_int("MAX_TOKENS", 800)
RELEVANCE_THRESHOLD = _get_float("RELEVANCE_THRESHOLD", 0.5)

# --- Ingestion ---
CHUNK_SIZE = _get_int("CHUNK_SIZE", 500)
CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 100)
