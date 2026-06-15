import pytest
from fastapi.testclient import TestClient

import src.api as api_mod
from src.api import app, get_db


@pytest.fixture
def client():
    # /ask normally opens a real DB connection; override it since we stub ask().
    app.dependency_overrides[get_db] = lambda: None
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ask_returns_answer_and_pages(client, monkeypatch):
    fake = {
        "query": "which bolt?",
        "answer": "Use the wing bolt [página 42]",
        "sources": [
            {"id": 1, "source": "cat.pdf", "chunk_index": 0,
             "page_number": 42, "distance": 0.1},
        ],
        "pages": [42],
        "min_distance": 0.1,
    }
    monkeypatch.setattr(api_mod, "ask", lambda conn, q, k: fake)

    r = client.post("/ask", json={"query": "which bolt?"})

    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Use the wing bolt [página 42]"
    assert body["pages"] == [42]
    assert body["sources"][0]["page_number"] == 42


def test_ask_trims_query_and_passes_top_k(client, monkeypatch):
    captured = {}

    def fake_ask(conn, q, k):
        captured["q"], captured["k"] = q, k
        return {"query": q, "answer": "ok", "sources": [], "pages": [],
                "min_distance": None}

    monkeypatch.setattr(api_mod, "ask", fake_ask)

    r = client.post("/ask", json={"query": "  hello  ", "top_k": 3})

    assert r.status_code == 200
    assert captured == {"q": "hello", "k": 3}


def test_ask_rejects_empty_query(client):
    # empty string fails schema validation (min_length=1)
    assert client.post("/ask", json={"query": ""}).status_code == 422


def test_ask_rejects_whitespace_query(client, monkeypatch):
    monkeypatch.setattr(api_mod, "ask", lambda conn, q, k: {})  # must not be reached
    assert client.post("/ask", json={"query": "   "}).status_code == 422


def test_ask_rejects_invalid_top_k(client):
    assert client.post("/ask", json={"query": "q", "top_k": 0}).status_code == 422


def test_pdf_404_when_missing(client, monkeypatch):
    monkeypatch.setattr(api_mod.config, "PDF_PATH", "/nope/missing.pdf")
    assert client.get("/pdf").status_code == 404


def test_pdf_serves_file(client, monkeypatch, tmp_path):
    f = tmp_path / "catalog.pdf"
    f.write_bytes(b"%PDF-1.4 fake pdf bytes")
    monkeypatch.setattr(api_mod.config, "PDF_PATH", str(f))

    r = client.get("/pdf")

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == b"%PDF-1.4 fake pdf bytes"
