# Etapa 3 — Retrieval y generación con citas de página

## Qué se construyó
El cierre del **backend** del *hilo conductor*: el `page_number` ahora viaja
**chunk → retrieval → cita**. `retrieve` devuelve la página de cada resultado y
`rag` arma el prompt para que el LLM cite `[página N]` y expone las páginas que
fundamentan la respuesta. Continúa [[02-ingestion-con-pagina]].

## Cambios
- **`src/retrieve.py`** — `SELECT ... page_number` y `page_number` en cada dict.
- **`src/rag.py`** — `build_prompt` cita por página; `ask` devuelve `sources` con
  `page_number` + un campo `pages`.
- **`src/main.py`** — la CLI muestra la página en cada fuente y la lista `pages`.
- **`tests/`** — `test_rag_citations.py` (nuevo) + `test_retrieve.py` actualizado.

## Teoría: cómo funciona el retrieval (para la entrevista)
1. **Mismo espacio vectorial.** La pregunta se embebe con el **mismo modelo** que
   los chunks; si no, pregunta y documentos no serían comparables.
2. **Búsqueda k-NN por distancia coseno.** Con el operador `<=>` de PGVector:
   `ORDER BY embedding <=> query_vec LIMIT k`. El coseno compara la **dirección**
   de los vectores (no la magnitud): 0 = misma dirección (idéntico), 2 = opuesta.
   El índice HNSW hace esa búsqueda aproximada y rápida.
3. **Gate de relevancia (anti-alucinación, heredado del base).** Si el chunk más
   cercano supera el umbral de distancia, NO se llama al LLM y se responde
   "no tengo info suficiente". Evita respuestas inventadas fuera de dominio.

## Decisiones técnicas y por qué
- **Citar por página, no por id de chunk.** El formato `[página N]` es lo que el
  usuario entiende y lo que el frontend convertirá en **link clickeable**. Pedimos
  un formato **exacto y estable** justamente para poder parsearlo con un regex
  simple (`\[página\s+(\d+)\]`).
- **`pages` = páginas de los chunks recuperados** (únicas, ordenadas, sin `None`).
  Son las que **fundamentan** la respuesta → insumo para el panel de "fuentes".
  Las páginas **realmente citadas** se obtienen del texto de la respuesta
  (parseando `[página N]`). Es una **separación de responsabilidades**: el backend
  entrega el material y las páginas candidatas; el frontend resuelve qué se
  clickea. Parsear la salida del LLM en el backend sería más frágil.
- **`page_number` puede ser `None`** (texto plano sin páginas): se muestra `n/a` y
  se excluye de `pages`. La feature apunta al PDF, donde todas tienen página.
- **Prompt reforzado:** regla explícita "nunca inventes páginas ni citas".

## Cómo se usa / flujo
`ask(conn, query)` →
```python
{
  "query": ...,
  "answer": "Use the wing bolt [página 42] ...",
  "sources": [{"id", "source", "chunk_index", "page_number", "distance"}, ...],
  "pages": [42, 57],          # páginas que fundamentan la respuesta
  "min_distance": 0.18,
}
```
El frontend (Etapas 4–6) parseará `[página N]` del `answer` para generar las
citas que saltan el visor del PDF.

## Estado / pendiente
- ✅ **32 tests passing** (mockeados, sin DB ni API).
- ✅ **Verificado end-to-end (2026-06-16):** `ask` real cita `[página 199]` y el gate
  rechaza lo fuera de dominio. Detalle y limitación de recall en [[08-validacion-end-to-end]].
- **Próximo (Etapa 4):** API FastAPI que expone `ask` por HTTP, sirve el PDF y
  habilita CORS para el frontend.

## Conceptos clave (para la entrevista)
- **k-NN / distancia coseno / por qué el mismo modelo de embeddings** para query y
  chunks.
- **Por qué un formato de cita parseable:** desacopla el backend (genera texto con
  `[página N]`) del frontend (lo vuelve interactivo).
