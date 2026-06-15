# Etapa 2 — Ingestion con metadata de página

## Qué se construyó
Se extendió la ingestión para que **cada chunk recuerde de qué página salió**. Es
el segundo eslabón del *hilo conductor* del `page_number`: extracción →
**chunk** → cita → click → salto en el visor. Reutiliza el pipeline existente
(`embed`, `db`); ver el sistema base en [[00-sistema-rag-existente]] y la
extracción en [[01-extraccion-pdf-ocr]].

## Cambios
- **`src/db.py`** — nueva columna `page_number INTEGER` en `documents`.
- **`src/ingest.py`** — `ingest_pages(...)`, refactor en funciones puras + I/O,
  y `content_hash` recompuesto.
- **`tests/test_ingest_pages.py`** — 10 tests nuevos (mockeados).

## Decisiones técnicas y por qué
1. **`page_number` nullable + migración `ADD COLUMN IF NOT EXISTS`.** Mismo
   estilo de migración que ya usaba `db.py` (idempotente). Nullable para que la
   ingestión de texto plano (`sample_docs.txt`, sin páginas) siga funcionando con
   `page_number = NULL`.
2. **Chunking por página (un chunk = una página).** Cada página se chunkea por
   separado, así cada chunk hereda el `page_number` de su página y **ningún chunk
   cruza el borde entre dos páginas**. Es lo que necesita una cita que salta a la
   página exacta, y encaja con un catálogo donde la información es local a la
   página. *Trade-off:* una idea que cruza el borde de página se parte en dos
   chunks; aceptable en este caso.
3. **`content_hash = sha256(source + page_number + content)`** (antes era solo
   `content`). En el catálogo hay texto repetido entre páginas
   (encabezados/pies). Con el hash viejo, el mismo texto en la pág. 5 y la 50
   colapsaba en **una sola fila** (`ON CONFLICT DO NOTHING`) y perdíamos una
   página citable. Incluyendo la página (y el source), quedan **filas distintas y
   citables**, y re-ingerir el mismo documento sigue siendo **idempotente**
   (mismos hashes → no duplica).
4. **`chunk_index` corrido global** dentro del documento (no se reinicia por
   página): mantiene el significado de "posición en el documento".
5. **Lógica pura separada de la I/O.** `_records_from_pages` (arma los records
   con su página) y `_content_hash` son funciones puras → se testean **sin DB ni
   API**. `_store_records` concentra el embed batch + el INSERT. Por eso pudimos
   validar la etapa entera con tests mockeados.

## Cómo se usa
- **Programático:** `ingest_pages(conn, pages, source)` donde `pages` es la lista
  `{page_number, text}` que produce `pdf_loader`.
- **CLI:** `python -m src.ingest <pages.json> [source]` ingiere un JSON de OCR
  (el de [[01-extraccion-pdf-ocr]]). Sin argumentos, ingiere el `sample_docs.txt`
  de siempre.
- **Flujo completo:** `pdf_loader` (OCR → JSON) → `ingest_pages` (chunk + embed +
  insert con `page_number`).

## Estado / pendiente
- ✅ **Verificado con 26 tests passing** (10 nuevos, mockeados — sin DB ni API).
- ⏳ **Corrida real end-to-end pendiente:** necesita `OPENAI_API_KEY` (los
  embeddings) para ingerir páginas reales del Cessna en Postgres.
- El `retrieve`/`rag` **todavía no exponen `page_number`**: eso es la **Etapa 3**
  (el SELECT y el prompt de citas por página).

## Conceptos clave (para la entrevista)
- **Idempotencia:** `content_hash` único + `ON CONFLICT DO NOTHING` → re-ingerir
  no duplica. La clave de dedup define qué se considera "el mismo chunk"; acá la
  movimos a `source + page_number + content` a propósito.
- **Por qué chunk-per-page:** una cita debe apuntar a una sola página; si un
  chunk mezclara dos páginas, la cita sería ambigua.
