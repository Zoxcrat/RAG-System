# PLAN — RAG sobre PDF técnico con citas clickeables

> Documento maestro del proyecto: mapa del roadmap y referencia de estado.
> Claude Code lo consulta al inicio de cada etapa para saber dónde estamos y qué
> falta, y lo actualiza al completar cada una.
>
> **Última actualización:** 2026-06-16 · **Estado general: 7/7 etapas + validación end-to-end real + búsqueda híbrida** ✅

---

## CONTEXTO

- **Proyecto:** extender un RAG existente para una entrevista técnica (será
  presencial y en vivo, así que el código debe entenderse y defenderse bien).
- **Objetivo final:** un sistema que procese un PDF técnico de ~670 páginas
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
  - ✅ *Verificado end-to-end* (2026-06-16, con key real) — ver "VALIDACIÓN END-TO-END".

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
  - ✅ *Verificado end-to-end* (2026-06-16, con key real) — ver "VALIDACIÓN END-TO-END".

### ETAPA 4 — Backend API REST (FastAPI)
- **Objetivo:** endpoints de health y de pregunta (query → respuesta + citas +
  chunks fuente). Servir el PDF. CORS para desarrollo local.
- **Archivos que toca:** `src/api.py` (nuevo), `src/config.py` (`PDF_PATH`,
  `CORS_ORIGINS`), `requirements.txt` (fastapi, uvicorn), `requirements-dev.txt`
  (httpx), `Dockerfile` (EXPOSE), `docker-compose.yml` (servicio `api`),
  `Makefile`, `tests/test_api.py`.
- **Estado:** ✅ **COMPLETADA (2026-06-15)**
- **Notas:**
  - `GET /health` → `{"status": "ok"}`; `POST /ask` (`{query, top_k?}` →
    `{answer, sources[...page_number], pages, min_distance}`, validado con
    Pydantic); `GET /pdf` (sirve el PDF con `FileResponse`).
  - CORS habilitado (configurable por `CORS_ORIGINS`, default `*` para dev).
  - Conexión a Postgres **por request** (dependency `get_db` con `yield`); un
    pool sería el próximo paso para más concurrencia.
  - Servicio `api` en docker-compose (reusa la imagen, `command` → uvicorn,
    puerto 8000). Targets `make api` (local) / `make docker-api`.
  - **Verificado:** 40 tests passing (8 de API con `TestClient`, mockeados) +
    smoke test del contenedor (`/health`, `/pdf`).
  - ✅ *Verificado end-to-end* (2026-06-16): `/ask` y `/pdf` por HTTP con key real.

### ETAPA 5 — Frontend React con visor PDF
- **Objetivo:** visor PDF.js, input de pregunta, área de respuesta, conexión con
  el backend.
- **Archivos que toca:** `frontend/` (Vite + React + TS): `src/App.tsx`,
  `src/components/PdfViewer.tsx`, `src/components/AskPanel.tsx`, `src/api.ts`,
  `src/types.ts` + config (package.json, vite, tsconfig).
- **Estado:** ✅ **COMPLETADA (2026-06-15)**
- **Notas:**
  - Vite + React + **TypeScript**; **react-pdf** (PDF.js) para el visor.
  - Layout: visor a la izquierda (`Document`/`Page` + nav prev/next), panel Q&A a
    la derecha (input → `POST /ask` → respuesta + `pages` + `sources`, con
    loading/error).
  - **Estado de página levantado a `App`** (lifting state up): visor y panel
    comparten `page`. Al responder, el visor salta a la primera página fuente —
    base para las citas clickeables de la E6.
  - Worker de PDF.js apuntado a `pdfjs-dist` vía `new URL(..., import.meta.url)`.
  - **Verificado:** `npm run build` (tsc + vite build) compila y tipa OK.
  - ✅ *Verificado en vivo* (2026-06-16): `npm run dev` + API real; las citas
    `[página N]` saltan el visor a la página correcta. Vulns npm → resueltas en E7.

### ETAPA 6 — Feature estrella: citas clickeables con salto a página
- **Objetivo:** citas clickeables que hacen saltar el visor a la página exacta.
- **Archivos que toca:** `frontend/src/citations.ts` (+ test),
  `components/AnswerText.tsx`, `components/AskPanel.tsx`, `App.tsx`/`App.css`.
- **Estado:** ✅ **COMPLETADA (2026-06-15)**
- **Notas:**
  - `citations.ts`: `parseAnswer` (función pura) parte el texto en segmentos de
    texto y citas (`[página N]`, regex tolerante a espacios).
  - `AnswerText.tsx`: renderiza cada cita como un **botón**; al click llama
    `onCite(page)`.
  - El click setea `page` en `App` → el `PdfViewer` (componente **controlado**)
    re-renderiza esa página (flujo de datos unidireccional de React). Al llegar
    una respuesta, además salta a la **primera página citada**.
  - **Cierra el hilo conductor:** extracción → chunk → retrieval → cita → click → salto.
  - **Verificado:** `npm run build` OK + **6 tests del parser** (vitest, primer
    test del frontend). Render visual: con `npm run dev` + backend con key.

### ETAPA 7 — Pulido y robustez
- **Objetivo:** manejo de errores, loading states, que se vea prolijo.
- **Archivos que toca:** `frontend/src/App.tsx`, `components/AskPanel.tsx`,
  `components/AnswerText.tsx`, `components/PdfViewer.tsx`, `App.css`.
- **Estado:** ✅ **COMPLETADA (2026-06-15)**
- **Notas:**
  - Estados: loading ("Searching…"), empty (hint inicial), error prolijo.
  - UX: enviar con ⌘/Ctrl+Enter, input "ir a página", y la cita de la página
    actual queda resaltada (`citation-active`).
  - **Code-split:** el visor se carga con `lazy`/`Suspense` → el bundle inicial
    bajó de **522 kB → 148 kB** (pdfjs queda en un chunk aparte). Sin warning.
  - **Vulnerabilidades npm:** las 6 son de **dev-deps** (vite/vitest), no de
    runtime; el fix safe no aplica y `--force` sube majors (riesgo de romper) →
    documentadas, no afectan lo que se sirve.
  - **Verificado:** `npm run build` OK (chunks separados) + 6 tests (vitest).

---

## VALIDACIÓN END-TO-END (2026-06-16)

Primera corrida con `OPENAI_API_KEY` real. Detalle y teoría en
[docs/08-validacion-end-to-end.md](docs/08-validacion-end-to-end.md).

- **OCR completo persistido:** las **670 páginas** OCR-eadas → `data/cessna_172_ocr.json`
  (gitignored, derivado del PDF). 0 páginas vacías; ~66% son tablas de partes densas,
  ~9% páginas de diagrama (casi sin texto, esperado).
- **Ingestión real:** 2605 chunks del catálogo en Postgres, `page_number` intacto en
  las 670 páginas. Costo total de la corrida: < 1 centavo.
- **Cadena completa OK:** `/ask` por HTTP cita `[página 199]` con datos reales; el
  frontend la vuelve botón y el visor salta. El **gate de relevancia** rechaza lo
  fuera de dominio (ej. "capital of France", distancia 0.735 > umbral 0.5).
- **2 bugs encontrados y arreglados** (solo aparecían con datos reales, los tests
  eran mockeados):
  1. `fix(embed)`: `embed_texts` mandaba todos los chunks en un request → la API tope
     a **2048 inputs**. Ahora batchea (≤2048). **Era bloqueante** para ingerir el catálogo.
  2. `fix(ingest)`: `cur.rowcount` tras `execute_values` reporta solo la última página
     interna (decía 5 en vez de 2605). Ahora cuenta con `RETURNING`.
- **Limitación de recall → RESUELTA con búsqueda híbrida** (2026-06-16, ver
  [docs/09-busqueda-hibrida.md](docs/09-busqueda-hibrida.md)). El vector puro perdía datos
  sepultados en chunks densos (ej. "headliner hanger", pág. 201). Se agregó un arm léxico
  (full-text de Postgres) fusionado con el vectorial vía **Reciprocal Rank Fusion**; ahora
  responde `0411680 [página 201]` y permite **buscar por número de parte**. El gate
  anti-alucinación sigue siendo vectorial. `DEFAULT_TOP_K` 5 → 10. 49 tests passing.
  - **Medido (2026-06-16, ver [docs/10-evaluacion.md](docs/10-evaluacion.md)):** `make eval`
    sobre un gold set de 11 preguntas → **recall@10 0.45 → 0.82** con híbrida (MRR casi
    igual: los rescates entran en ranks profundos → lo que arreglaría el **reranking**).
    Gate: 2/2 out-of-domain rechazadas.
  - **Reranking HECHO (2026-06-16, ver [docs/11-reranking.md](docs/11-reranking.md)):**
    reranker LLM listwise sobre los 20 candidatos del híbrido → **recall@5 0.73 → 0.91,
    MRR@10 0.39 → 0.69**. Arregla el *orden* (lo que el híbrido no movía). El gate corre
    antes del rerank; fail-open. Reusa `gpt-4o-mini` (sin cross-encoder/torch).
  - *Próximo en esta línea:* chunking estructural (por fila), query expansion para los
    casos que ni entran al pool (ej. radio shelf p202).
- **Agregación HECHA (2026-06, ver [docs/15-agregacion-text-to-sql.md](docs/15-agregacion-text-to-sql.md)):**
  preguntas de "cuántos / listá todos / el más común" (que el top-k no puede). Tabla `parts`
  estructurada (7225 partes) + router de intención + **text-to-SQL con candados** (solo SELECT,
  read-only, LIMIT) + **fallback** al semántico si la SQL no trae filas. Responde las preguntas
  de agregación de la entrevista; las puntuales siguen yendo a híbrida+rerank.

---

## REGLAS DE TRABAJO

- **Una etapa a la vez**, esperando confirmación de Franco antes de avanzar a la
  siguiente.
- **Al completar cada etapa:** actualizar el estado en este `PLAN.md` y la
  documentación en `/docs` (en español), según `CLAUDE.md`.
- **Código en inglés, documentación en español.**
- Pensar como ingeniero y a futuro (no agregar features porque sí); dejar el
  código entendible y defendible para la entrevista en vivo.
