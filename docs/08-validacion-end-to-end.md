# Etapa 8 — Validación end-to-end con LLM real (2026-06-16)

Primera corrida completa con `OPENAI_API_KEY` real: OCR de las 670 páginas →
ingestión → retrieval → generación con citas → frontend. Cierra el único pendiente
que quedaba (la cadena con el LLM real). Continúa [[07-pulido-robustez]].

## Qué se hizo
1. **OCR completo persistido.** Se corrieron las **670 páginas** (no ~600 como se
   estimaba) y se guardó el cache en `data/cessna_172_ocr.json` (~998 KB, gitignored:
   es derivado del PDF, ver [[01-extraccion-pdf-ocr]]).
2. **Ingestión real** del catálogo: 2605 chunks en Postgres, `page_number` intacto
   en las 670 páginas.
3. **Q&A real** validado por CLI y por HTTP (`/ask`, `/pdf`) + frontend en vivo.
4. **Costo total: < 1 centavo** (`text-embedding-3-small` + `gpt-4o-mini`).

## Calidad del OCR (sobre las 670 páginas)
| Bucket | % | Qué son |
|---|---|---|
| ≥600 chars | ~66% | Tablas de partes densas (el contenido que responde el RAG) |
| 150–600 | ~24% | Tablas chicas, avisos, índices |
| <150 chars | ~9% | **Páginas de diagrama** (solo caption + ruido) — esperado |
| 0 (vacías) | 0% | Ninguna página falló el OCR |

Las tablas salen legibles (`0512029-8 STRINGER ASSEMBLY-AFT CABIN TOP RH`), con ruido
de carácter (`O`↔`0`: "STRLNGER"). Los **diagramas** son imágenes: el OCR solo rescata
el caption, pero la página sigue siendo **citable** y el humano ve el dibujo en el
visor cuando una cita salta ahí. La capa de texto embebida del PDF es basura (confirma
la decisión de re-OCR-ear, no usar `get_text()`).

## La cadena estrella, verificada con datos reales
- **Pregunta de dominio:** *"What stringer assembly is listed for the aft cabin top?"*
  → respuesta con part numbers y cita **`[página 199]`** → el frontend la vuelve botón
  → click → el visor salta a la 199. El `page_number` viaja entero: OCR → chunk →
  retrieval → cita → click → salto.
- **Gate de relevancia (anti-alucinación):** *"What is the capital of France?"* →
  distancia mínima 0.735 > umbral 0.5 → **no llama al LLM**, responde "no info". Funciona.

## Dos bugs que solo aparecen con datos reales
Los tests eran 100% mockeados, así que estos dos nunca habían salido. Son buen material
de entrevista porque son límites concretos de las APIs/librerías reales.

### 1. Límite de 2048 inputs por request de embeddings (BLOQUEANTE)
`embed_texts` mandaba **todos** los chunks en una sola llamada
`embeddings.create(input=texts)`. La API de OpenAI rechaza con **400** si el array
tiene más de **2048** elementos (y además hay un tope de tokens totales por request).
Con sample_docs (pocos chunks) nunca se notó; con el catálogo (2605 chunks) explotó.
- **Fix:** `embed_texts` ahora batchea en lotes de `EMBED_BATCH_SIZE` (1000, con
  headroom). Cada response trae `index` **relativo a su batch**, así que se ordena
  dentro del lote y se concatena en orden → el orden global se preserva.
- **Teoría:** las APIs de embeddings tienen límites por request (cantidad de inputs y
  tokens). Batchear no es opcional a escala; es parte de un cliente correcto.

### 2. `cur.rowcount` con `execute_values` sub-reporta (cosmético)
`_store_records` devolvía `cur.rowcount`, que daba **5** para un insert de **2605**
filas. `psycopg2.extras.execute_values` parte el INSERT en **páginas internas**
(`page_size`=100 por defecto) y `rowcount` refleja solo la **última** página.
- **Fix:** usar `fetch=True` + `RETURNING id` y contar las filas devueltas. Con
  `ON CONFLICT DO NOTHING`, `RETURNING` trae solo las **realmente insertadas** → conteo
  exacto, sin importar el paginado.
- **Teoría:** una optimización de la librería (batch del lado cliente) cambia la
  semántica de `rowcount`. `RETURNING` es la forma SQL canónica de saber qué se insertó.

## Limitación conocida: recall del retrieval
*"What is the part number for the headliner hanger?"* **falló**: el dato existe
(`0411680 HANGER~HEADLINER`, pág. 201) pero el retrieval no trajo la 201 en el top-k.
Por qué:
- El dato está **sepultado** en un chunk de 500 chars lleno de números de parte → su
  embedding queda "diluido".
- **Ruido de OCR** (`HANGER~HEADLINER`) vs la query ("headliner hanger").
- **Chunking por ventana de caracteres**, no por fila → corta filas de la tabla.

No es un bug: es el techo del **retrieval semántico puro** sobre tablas densas. Es
exactamente lo que motiva el roadmap:
- **Búsqueda híbrida** (vector + keyword/BM25): un número de parte o "HEADLINER" matchea
  por lexical aunque el coseno no lo priorice.
- **Chunking estructural** (por fila/sección, no por 500 chars).
- **Reranking** con cross-encoder sobre el top-k.
- **Evaluación** (recall@k, MRR) para medir esto en vez de adivinar.

## Conceptos clave (para la entrevista)
- **Por qué los tests mockeados no alcanzan:** validan la lógica, no los límites reales
  de las APIs (2048 inputs, semántica de `rowcount`). Una corrida real es otra capa de test.
- **Batching como requisito, no optimización**, en clientes de embeddings.
- **`RETURNING` vs `rowcount`** para contar inserts idempotentes.
- **Recall vs precisión** y por qué el baseline semántico puro falla en tablas densas.
