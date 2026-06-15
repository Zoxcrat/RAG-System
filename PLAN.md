# PLAN — RAG sobre PDF técnico con citas clickeables

> Documento maestro del proyecto: mapa del roadmap y referencia de estado.
> Claude Code lo consulta al inicio de cada etapa para saber dónde estamos y qué
> falta, y lo actualiza al completar cada una.
>
> **Última actualización:** 2026-06-15

---

## CONTEXTO

- **Proyecto:** extender un RAG existente para una entrevista técnica (será
  presencial y en vivo, así que el código debe entenderse y defenderse bien).
- **Objetivo final:** un sistema que procese un PDF técnico de ~600 páginas
  (catálogo de partes de aviación, escaneado, con OCR parcial), permita **Q&A en
  tiempo real**, muestre **citas con salto a la página exacta del PDF al hacer
  clic**, y tenga una **GUI web básica**.
- **Punto de partida:** RAG base ya funcionando — Postgres + PGVector, embeddings
  de OpenAI, retrieval por cosine distance, generación con citas y relevance
  threshold (anti-alucinación). Detalle en [docs/00-sistema-rag-existente.md](docs/00-sistema-rag-existente.md).

---

## DECISIONES TÉCNICAS FIJADAS

- **OCR sí, texto embebido no.** El PDF tiene una capa de OCR parcial e
  imperfecta → NO usar el texto embebido. Renderizar cada página y aplicar OCR
  moderno (**PyMuPDF + pytesseract**).
- **El número de página es el hilo conductor.** `page_number` debe viajar de
  punta a punta: extracción → metadata del chunk → cita → click → salto en el
  visor. Si se rompe en cualquier eslabón, se cae la feature estrella.
- **Stack:**
  - Backend: Python (extiende el RAG actual) + **API FastAPI**.
  - OCR: **PyMuPDF + pytesseract** (Tesseract dentro de la imagen Docker, no en
    la máquina del host — reproducibilidad).
  - Frontend: **React + PDF.js**.
- **Infra:** Docker. Código y dependencias se hornean en la imagen; sin
  bind-mount de la carpeta iCloud; estado en named volumes. (Política heredada
  del proyecto base.)

---

## ROADMAP POR ETAPAS

> Estados posibles: **PENDIENTE** / **EN PROGRESO** / **COMPLETADA**.

### ETAPA 1 — Extracción de PDF con OCR
- **Objetivo:** módulo `src/pdf_loader.py` que renderiza páginas, aplica OCR,
  devuelve lista de `{page_number, text}`, con guardado/carga en JSON.
- **Archivos que toca:** `src/pdf_loader.py`, `requirements.txt`, `Dockerfile`,
  `Makefile`, `data/` (PDF de prueba).
- **Estado:** ✅ **COMPLETADA (2026-06-15)**
- **Notas:**
  - `extract_pages_from_pdf(pdf_path, dpi=200, max_pages=None, lang="eng")`:
    render con PyMuPDF (zoom = `dpi/72`) → OCR con pytesseract. Errores aislados
    por página (warning a `stderr` + `text=""`, no aborta). Fail-fast si falta
    Tesseract.
  - `save_extracted_text` / `load_extracted_text`: cache JSON (el OCR es caro,
    se corre una sola vez).
  - Tesseract instalado **en la imagen Docker**; PDF movido a `data/` (se hornea
    en la imagen). Targets `make ocr` (local) y `make docker-ocr` (contenedor).
  - **Verificado:** OCR corrido en contenedor sobre el Cessna; lee bien el texto
    (con ruido típico de escaneo viejo). Doc: [docs/01-extraccion-pdf-ocr.md](docs/01-extraccion-pdf-ocr.md).
  - *Pendiente opcional para más adelante:* preprocesado de imagen (grises /
    binarización / deskew) o subir DPI si la calidad del retrieval lo pide.

### ETAPA 2 — Ingestion con metadata de página
- **Objetivo:** chunking/ingestion que guarda `page_number` por chunk. Actualizar
  el schema si hace falta.
- **Archivos que toca:** `src/db.py` (columna `page_number`), `src/ingest.py`
  (chunking por página + ingestión con `page_number`), `tests/test_ingest_pages.py`.
- **Estado:** ✅ **COMPLETADA (2026-06-15)**
- **Notas:**
  - `db.py`: columna `page_number INTEGER` (nullable) en `documents`, con
    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (migración compatible).
  - `ingest.py`: `ingest_pages(conn, pages, source)` chunkea **cada página por
    separado** → cada chunk hereda su `page_number` (un chunk = una página).
    `chunk_index` corre a lo largo del documento; páginas con OCR vacío no
    aportan chunks. `ingest_file` (texto plano) sigue andando con `page_number`
    NULL. La lógica pura (`_records_from_pages`, `_content_hash`) está separada
    de la I/O (`_store_records`) para testear sin DB ni API.
  - `_content_hash` ahora combina `source + page_number + content`: el mismo
    boilerplate en páginas distintas queda como filas **distintas y citables**, y
    la ingestión sigue siendo idempotente.
  - CLI: `python -m src.ingest <pages.json> [source]` ingiere un JSON de OCR.
  - **Verificado:** 26 tests passing (10 nuevos, mockeados, sin DB/API).
  - *Pendiente:* corrida real end-to-end (necesita `OPENAI_API_KEY`).

### ETAPA 3 — Retrieval y generación con citas de página
- **Objetivo:** el retrieval devuelve `page_number`; la generación cita
  `[página X]` y devuelve las páginas usadas.
- **Archivos que toca:** `src/retrieve.py`, `src/rag.py`, `src/main.py`
  (presentación), `tests/test_retrieve.py`, `tests/test_rag_citations.py`.
- **Estado:** ✅ **COMPLETADA (2026-06-15)**
- **Notas:**
  - `retrieve.py`: el `SELECT` ahora trae `page_number` y cada resultado lo
    incluye (puede ser `None` para texto plano).
  - `rag.py`: `build_prompt` expone `page="N"` por chunk e instruye a citar en el
    formato exacto `[página N]` (parseable por el frontend). `ask` agrega
    `page_number` a cada `source` y un campo `pages` = páginas únicas y ordenadas
    de los chunks recuperados (las que fundamentan la respuesta; las realmente
    citadas se parsean del texto `[página N]`).
  - `main.py`: la CLI muestra la página en cada fuente y la lista `pages`.
  - **Verificado:** 32 tests passing (6 nuevos + `test_retrieve` actualizado;
    mockeados, sin DB/API).
  - *Pendiente:* corrida real end-to-end (necesita `OPENAI_API_KEY`).

### ETAPA 4 — Backend API REST (FastAPI)
- **Objetivo:** endpoints de health y de pregunta (query → respuesta + citas +
  chunks fuente). Servir el PDF. CORS para desarrollo local.
- **Archivos que toca:** nuevo `src/api.py` (FastAPI), `requirements.txt`
  (fastapi, uvicorn), `Dockerfile`/`docker-compose.yml` (servicio API + puerto),
  endpoint estático para el PDF.
- **Estado:** ⬜ PENDIENTE
- **Notas:** `GET /health`; `POST /ask` (devuelve answer + citas con
  `page_number` + chunks fuente); `GET /pdf` (sirve el PDF para el visor). CORS
  habilitado para el front en local.

### ETAPA 5 — Frontend React con visor PDF
- **Objetivo:** visor PDF.js, input de pregunta, área de respuesta, conexión con
  el backend.
- **Archivos que toca:** nuevo `frontend/` (React + PDF.js) y su tooling.
- **Estado:** ⬜ PENDIENTE
- **Notas:** layout básico: visor del PDF a un lado, panel de Q&A al otro.
  Consume `POST /ask` y muestra respuesta + citas.

### ETAPA 6 — Feature estrella: citas clickeables con salto a página
- **Objetivo:** citas clickeables que hacen saltar el visor a la página exacta.
- **Archivos que toca:** `frontend/` (render de citas como links + control del
  visor PDF.js); el backend ya provee `page_number` (Etapas 3–4).
- **Estado:** ⬜ PENDIENTE
- **Notas:** es el cierre del "hilo conductor" del `page_number`. Click en
  `[página X]` → el visor navega a esa página.

### ETAPA 7 — Pulido y robustez
- **Objetivo:** manejo de errores, loading states, que se vea prolijo.
- **Archivos que toca:** `frontend/` y `src/api.py` (mensajes de error,
  estados de carga, estilos).
- **Estado:** ⬜ PENDIENTE
- **Notas:** estados de loading/empty/error, feedback claro al usuario,
  prolijidad visual para la demo en vivo.

---

## REGLAS DE TRABAJO

- **Una etapa a la vez**, esperando confirmación de Franco antes de avanzar a la
  siguiente.
- **Al completar cada etapa:** actualizar el estado en este `PLAN.md` y la
  documentación en `/docs` (en español), según `CLAUDE.md`.
- **Código en inglés, documentación en español.**
- Pensar como ingeniero y a futuro (no agregar features porque sí); dejar el
  código entendible y defendible para la entrevista en vivo.
