.PHONY: help up down ps logs init ingest ask test compile restart clean install install-dev

PY := .venv/bin/python

help:
	@echo "Mini-RAG — daily commands"
	@echo ""
	@echo "  make install      Create venv (uv) and install prod dependencies"
	@echo "  make install-dev  Same as install, plus pytest"
	@echo ""
	@echo "  make up           Start the Postgres + PGVector container (waits until ready)"
	@echo "  make down         Stop the container (data is kept on the volume)"
	@echo "  make ps           Show container status"
	@echo "  make logs         Tail the container logs"
	@echo "  make restart      Restart the container"
	@echo ""
	@echo "  make init         Initialize the DB schema"
	@echo "  make ingest       Embed and index data/sample_docs.txt"
	@echo "  make ask          Run the interactive RAG demo"
	@echo ""
	@echo "  make test         Run the pytest suite (no API calls)"
	@echo "  make compile      Verify all src/ modules import cleanly"
	@echo ""
	@echo "  make clean        Stop AND drop the data volume (LOSES INGESTED CHUNKS)"

install:
	uv venv --python 3.12
	uv pip install -r requirements.txt

install-dev:
	uv venv --python 3.12
	uv pip install -r requirements-dev.txt

up:
	docker compose up -d
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
