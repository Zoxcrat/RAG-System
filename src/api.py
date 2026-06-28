"""FastAPI HTTP layer for the RAG pipeline: /health, /ask, /pdf, and the static UI."""
import base64
import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src import config
from src.db import close_pool, get_pool
from src.answer.rag import ask


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_pool()  # release pooled connections on graceful shutdown


app = FastAPI(title="Aviation Parts RAG API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_password(request: Request, call_next):
    """Gate the whole app behind HTTP Basic auth when DEMO_PASSWORD is set."""
    if config.DEMO_PASSWORD:
        header = request.headers.get("Authorization", "")
        ok = False
        if header.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
                ok = secrets.compare_digest(pw, config.DEMO_PASSWORD) and (
                    not config.DEMO_USER or secrets.compare_digest(user, config.DEMO_USER)
                )
            except Exception:  # malformed header -> treat as unauthorized
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return await call_next(request)


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language question.")
    top_k: Optional[int] = Field(default=None, gt=0, le=50)


class Source(BaseModel):
    id: int
    source: Optional[str] = None
    chunk_index: Optional[int] = None
    page_number: Optional[int] = None
    distance: Optional[float] = None


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[Source]
    pages: list[int]
    min_distance: Optional[float] = None
    # "lookup" (semantic) or "aggregate" (structured); sql is the query run when aggregate.
    mode: str = "lookup"
    sql: Optional[str] = None


def get_db():
    """Borrow a pooled connection for the request and return it clean."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        conn.rollback()  # never hand a transaction back to the pool
        pool.putconn(conn)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest, conn=Depends(get_db)) -> dict:
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must not be empty")

    top_k = config.DEFAULT_TOP_K if req.top_k is None else req.top_k
    try:
        return ask(conn, query, top_k)
    except Exception as exc:  # clean JSON error instead of a bare 500
        raise HTTPException(status_code=500, detail=f"Failed to answer: {exc}")


@app.get("/pdf")
def pdf() -> FileResponse:
    path = config.PDF_PATH
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF not found on the server.")
    return FileResponse(
        path, media_type="application/pdf", filename=os.path.basename(path)
    )


# Serve the built frontend from the same origin (one service, no CORS in prod).
# Mounted last so the API routes above take precedence.
if os.path.isdir(config.FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
