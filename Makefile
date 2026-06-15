.PHONY: help up down ps logs init ingest ask test compile restart clean install install-dev ocr api \
        docker-build docker-up docker-ingest docker-ask docker-down docker-ocr docker-api

PY := .venv/bin/python
PDF ?= data/Cessna 172 Parts Catalog (1963-1974).pdf

help:
	@echo "Mini-RAG"
	@echo ""
	@echo "Run everything in Docker (no local Python needed):"
	@echo "  make docker-up      Build the image, start Postgres, seed the schema and data"
	@echo "  make docker-ask     Open the interactive RAG demo inside the container"
	@echo "  make docker-ingest  Re-run ingestion inside the container"
	@echo "  make docker-ocr     OCR the first pages of a PDF in the container (PDF=path)"
	@echo "  make docker-api     Run the FastAPI backend in the container (port 8000)"
	@echo "  make docker-down    Stop everything"
	@echo ""
	@echo "Local workflow (Python via uv, Postgres in Docker):"
	@echo "  make install-dev    Create venv (uv) and install deps + pytest"
	@echo "  make up             Start the Postgres container (waits until ready)"
	@echo "  make ingest         Embed and index data/sample_docs.txt"
	@echo "  make ask            Run the interactive RAG demo"
	@echo "  make test           Run the pytest suite (no API calls)"
	@echo "  make ocr            OCR a PDF locally (needs tesseract; PDF=path)"
	@echo "  make api            Run the FastAPI backend locally (uvicorn, port 8000)"
	@echo ""
	@echo "  make down           Stop the container (keeps the data volume)"
	@echo "  make clean          Stop AND drop the data volume (loses ingested chunks)"

install:
	uv venv --python 3.12
	uv pip install -r requirements.txt

install-dev:
	uv venv --python 3.12
	uv pip install -r requirements-dev.txt

up:
	docker compose up -d postgres
	@until docker compose exec -T postgres pg_isready -U rag_user -d rag_db >/dev/null 2>&1; do sleep 1; done
	@echo "Postgres ready on localhost:5432"

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f postgres

restart:
	docker compose restart

init: up
	$(PY) -m src.db

ingest: up
	$(PY) -m src.ingest

ask: up
	$(PY) -m src.main

test:
	$(PY) -m pytest

compile:
	$(PY) -c "import src.db, src.embed, src.ingest, src.retrieve, src.rag, src.main; print('all modules import OK')"

clean:
	docker compose down -v

# --- Fully containerized workflow ---

docker-build:
	docker compose build

docker-up: docker-build
	docker compose up -d postgres
	@until docker compose exec -T postgres pg_isready -U rag_user -d rag_db >/dev/null 2>&1; do sleep 1; done
	docker compose run --rm app python -m src.ingest
	@echo "Stack ready. Run 'make docker-ask' to query it."

docker-ingest:
	docker compose run --rm app python -m src.ingest

docker-ask:
	docker compose run --rm app python -m src.main

docker-down:
	docker compose down

# --- OCR / PDF extraction (step 1 of the technical-PDF pipeline) ---

# Override PDF to point at another file, e.g. `make docker-ocr PDF=data/other.pdf`.
ocr:
	$(PY) -m src.pdf_loader "$(PDF)"

docker-ocr: docker-build
	docker compose run --rm --no-deps --entrypoint python app -m src.pdf_loader "$(PDF)"

# --- API (FastAPI backend) ---

api:
	$(PY) -m uvicorn src.api:app --reload --port 8000

docker-api: docker-build
	docker compose up api
