# Etapa 14 — Cómo extender el código (por si te piden agregar algo)

Si en la entrevista te piden "agregá X", lo importante es **saber dónde toca** y razonar en
voz alta. Esta es la guía. Conocé el **mapa de módulos** y los patrones del proyecto.

---

## Mapa mental de los módulos (memorizalo)
```
config.py   → toda la config (único que lee env). Si agregás un parámetro, va acá.
pdf_loader  → PDF → OCR → JSON.           (extracción)
db.py       → schema, conexión, índices.  (toca acá si cambia el modelo de datos)
embed.py    → texto → vectores (batched).
ingest.py   → chunk-por-página → embed → INSERT idempotente.
retrieve.py → vector + keyword + RRF (hybrid).   (toca acá si cambia la búsqueda)
rerank.py   → reordena candidatos con LLM.
rag.py      → prompt + gate + rerank + generación.  (orquesta el query)
api.py      → endpoints HTTP.             (toca acá si agregás un endpoint)
main.py     → CLI.
```
**Patrones del proyecto** (respetalos al extender):
- **Config centralizada**: cualquier parámetro nuevo → `config.py`, nunca `os.getenv` suelto.
- **Lógica pura separada de I/O**: las funciones puras (`chunk_text`, `_records_from_pages`,
  `reciprocal_rank_fusion`, `_parse_ranking`) se testean **sin DB ni API** (mockeado).
- **Type hints en todo. Errores explícitos. Batch sobre loops.**

---

## Pedidos comunes → dónde toca

### "Agregá un endpoint" (ej. `GET /pages?query=` que devuelva solo las páginas)
- **`api.py`**: nueva función con decorador `@app.get(...)`, modelo Pydantic para la
  respuesta, usá la dependency `get_db`. Reusá `ask`/`retrieve_hybrid`.
- Test en `tests/test_api.py` con `TestClient` (mockeando el pipeline).

### "Filtrá por metadata" (ej. solo cierta sección/figura, o por `source`)
- **`db.py`**: si el campo no existe, agregalo (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`)
  y guardalo en `ingest.py`.
- **`retrieve.py`**: agregá un `WHERE source = %s` (o el filtro) a las dos arms. Acá brilla
  Postgres: **filtro + búsqueda vectorial en el mismo SQL**, sin infra extra.
- Pasá el filtro como parámetro desde `rag.ask` / `api`.

### "Cambiá el chunking" (ej. por oraciones, o más chico)
- **`ingest.py` → `chunk_text`** (es pura → fácil de testear). O `_records_from_pages` si
  cambia la unidad. Ojo: si re-chunkás, hay que **re-ingestar** (re-embeber).
- Medí el impacto con **`make eval`** (recall@k / MRR).

### "Cambiá el modelo de embeddings"
- **`config.py`**: `EMBEDDING_MODEL` **y** `EMBEDDING_DIM` (la dimensión es parte del schema
  → cambiarla implica **migrar la columna `vector(N)` y re-embeber todo**). Mencioná ese costo.

### "Agregá streaming de la respuesta"
- **`api.py`**: `StreamingResponse` + Server-Sent Events; **`rag.py`**: usar
  `stream=True` en el cliente OpenAI y `yield` los tokens. El frontend consume el stream.

### "Ingerí otro PDF / otro tipo de doc"
- Poné el PDF en `data/`, corré OCR (`pdf_loader`), `ingest_pages`. Para texto plano ya está
  `ingest_file` (con `page_number=NULL`). La arquitectura ya es multi-fuente (`source`).

### "Mejorá el retrieval para el caso que falla (p202)"
- Es gap de **recall del retrieval** (no entra ni al pool). Opciones: **query expansion**
  (reformular/expandir la query con sinónimos antes de buscar), **chunking estructural**, o
  bajar el umbral del keyword. Medí con `make eval`.

### "Agregá memoria / multi-turno (conversación)"
- **`rag.py` / `api.py`**: pasar el historial; para follow-ups, **reescribir la query**
  (condensar la pregunta con el contexto previo) antes del retrieval. Cuidado con el costo
  de tokens.

### "Tuneá el sistema"
- Todo es config: `DEFAULT_TOP_K`, `RRF_K`, `RETRIEVAL_CANDIDATES`, `RERANK_CANDIDATES`,
  `RELEVANCE_THRESHOLD`, `CHUNK_SIZE/OVERLAP`. Cambiás en `config.py` y **medís con `make eval`**
  (esa es la respuesta correcta: no tunear a ojo).

---

## Ejemplo trabajado: filtro por `source` (cómo lo diría)
> "Agrego un parámetro `source` opcional a `retrieve_hybrid`. En las dos arms, si viene,
> sumo `WHERE source = %s` (en la vectorial, antes del `ORDER BY distance`; en la léxica,
> junto al `tsv @@ q`). Lo expongo en `ask` y en `/ask`. Como es Postgres, el filtro y la
> búsqueda van en el mismo query — no necesito una vector DB con filtrado aparte. Y agrego
> un test mockeado que verifica que el SQL incluye el `WHERE`."

---

## Cómo testear lo que agregás (patrón del repo)
- **Lógica pura** → test directo, sin mocks (ej. `chunk_text`, `reciprocal_rank_fusion`).
- **I/O (DB/OpenAI)** → mockeá: `monkeypatch.setattr(modulo, "embed_texts", fake)`,
  `FakeConn/FakeCursor` para la DB, fake client para OpenAI. Mirá `tests/` como plantilla.
- Corré `make test` (rápido, sin red) y, si tocaste retrieval, `make eval` (con DB + key).

## Conceptos clave (para la entrevista)
- **Saber DÓNDE toca cada cambio** demuestra que entendés la arquitectura, no solo que
  funciona.
- **"Lo mido con `make eval`"** es la respuesta de ingeniería a cualquier cambio de calidad.
- **Respetar los patrones** (config central, pura vs I/O, mockeo) = código consistente y
  defendible.
