# Etapa 12 — Banco de preguntas de entrevista

Preguntas anticipadas con respuestas afiladas. **Practicalas en voz alta** (recall activo).
Agrupadas por tema. Las respuestas son cortas a propósito: son el "núcleo" que después
expandís.

---

## 0. El pitch (60 segundos)
> "Es un RAG sobre un catálogo de partes escaneado del Cessna 172 (~670 páginas).
> Como el PDF es un escaneo con OCR embebido malo, **re-OCR-eo** cada página con Tesseract.
> Indexo chunk-por-página arrastrando el `page_number`, que es el **hilo conductor**: viaja
> hasta la cita `[página N]`, que el frontend vuelve un **botón que salta el visor a esa
> página**. El retrieval es **híbrido** (vector + full-text, fusionado con RRF) y después
> un **reranker LLM** reordena. Hay un **gate anti-alucinación** y lo medí con un
> **harness de evaluación** (recall@5 0.45→0.91 del baseline al sistema completo).
> Backend FastAPI, frontend React."

---

## 1. RAG / fundamentos
- **¿Qué es RAG y por qué?** Recuperás contexto relevante y se lo das al LLM para que
  responda *grounded*. Resuelve: conocimiento privado/actualizado, reduce alucinaciones,
  permite **citar fuentes**, más barato que fine-tuning.
- **¿RAG vs fine-tuning?** RAG = conocimiento (datos que cambian, citables). Fine-tuning =
  comportamiento/formato/estilo. Acá necesito *hechos citables del catálogo* → RAG.
- **¿Qué es un embedding?** Un vector que captura el **significado** del texto; textos
  parecidos → vectores cercanos. Pregunta y documentos se embeben con el **mismo modelo**
  para que vivan en el mismo espacio y sean comparables.

## 2. OCR / ingesta
- **¿Por qué OCR y no `get_text()`?** La capa embebida es basura (mostrás el ejemplo:
  `"illustrated parts dialog"`, `"C % S M ~ Z"`). Re-OCR desde la imagen renderizada es la
  única fuente confiable.
- **¿Por qué chunk-por-página?** Para que cada chunk tenga **una** página exacta → la cita
  `[página N]` es inequívoca. *Trade-off:* una idea que cruza el borde de página se parte.
- **¿Por qué cachear el OCR a JSON?** Es el paso caro (segundos/página × 670). Se corre una
  vez; las etapas siguientes leen el JSON.
- **¿Idempotencia?** `content_hash = sha256(source + page_number + content)` + índice único
  + `ON CONFLICT DO NOTHING`. Re-ingerir no duplica. Incluyo la página para que el
  boilerplate repetido entre páginas quede como filas distintas y **citables**.

## 3. Vector search
- **¿Por qué Postgres + PGVector y no Pinecone/Weaviate?** Un solo sistema guarda vectores +
  texto + metadata + full-text, con SQL/transacciones y sin infra extra. Correcto a esta
  escala, y habilita híbrida y filtros `WHERE` gratis. *En producción a gran escala* podría
  migrar a una vector DB dedicada o a `pgvector` con quantization.
- **¿HNSW vs IVFFlat?** HNSW: grafo navegable, **mejor recall/latencia**, más memoria e
  inserts más lentos (bueno read-heavy). IVFFlat: clustering, menos memoria, hay que
  entrenar y elegir `nlist`/`nprobe`. Elegí HNSW por recall.
- **¿Coseno vs dot product vs euclidiana?** Coseno compara **dirección**, no magnitud — lo
  estándar para embeddings de texto. Rango 0 (idéntico) a 2 (opuesto).
- **¿Qué es ANN (búsqueda aproximada)?** Cambiás un poco de recall por **mucha** velocidad;
  a escala, exacto (kNN puro) no escala.

## 4. Híbrida + RRF
- **¿Por qué híbrida?** El vector entiende *significado* pero **diluye** tokens literales
  (un nº de parte sepultado en un chunk denso). El full-text (keyword) los agarra exacto.
  Fallan en lugares distintos → se complementan. (Caso real: "headliner hanger".)
- **¿Qué es el full-text de Postgres?** `tsvector` (texto → lexemas stemmeados), `tsquery`,
  `ts_rank`, índice **GIN**. Es BM25-like (no exactamente BM25).
- **¿Qué es RRF?** Reciprocal Rank Fusion: `score = Σ 1/(k+rank)`. Combina rankings usando
  **solo el rank**, sin normalizar scores incomparables (distancia coseno vs ts_rank).
- **Sutilezas que resolví:** el OCR pega palabras (`HANGER~HEADLINER`→lexema `~headliner`)
  → normalizo `~ = |` antes de tokenizar; y el chunking parte términos → uso semántica **OR**.

## 5. Reranking
- **¿Qué es y por qué?** El retrieval es rápido pero ordena grueso (hits en rank profundo).
  El reranker mira el par (pregunta, pasaje) **junto** → más preciso. Corre solo sobre el
  top-N. Subió MRR@10 0.39→0.69.
- **¿Bi-encoder vs cross-encoder?** Bi-encoder (embeddings): precomputás, rápido, comparás
  por coseno. Cross-encoder: procesa pregunta+pasaje juntos, más preciso, **no precomputable**
  → solo sobre pocos candidatos.
- **¿Por qué LLM y no cross-encoder?** Para no meter torch (~1-2 GB) en la imagen. *Prod:*
  cross-encoder dedicado o Cohere Rerank. (Trade-off consciente.)
- **¿El reranker arregla el retrieval?** No: solo **reordena lo que ya vino**. Si el dato no
  está en el pool, no hay rerank que lo salve (caso p202).

## 6. Generación / anti-alucinación
- **¿Cómo evitás alucinaciones?** (1) Prompt *grounded*: "respondé solo con el contexto".
  (2) **Gate de relevancia**: si la mejor distancia coseno > umbral (0.5), **no llamo al LLM**
  y respondo "no tengo info". (3) `temperature=0`. (4) Citas verificables por el humano.
- **¿Por qué `temperature=0`?** Determinista, fiel al contexto, auditable y testeable.
- **¿Y si igual inventa?** El gate y el prompt reducen, no eliminan. Por eso las **citas**:
  el humano verifica en el PDF. Próximo paso: faithfulness eval (LLM-judge).

## 7. Evaluación
- **¿Cómo sabés que mejoró?** No "a ojo": **gold set** (11 preguntas, ground truth = la
  página cuyo OCR contiene la respuesta) + `recall@k` y `MRR@k`. `make eval`.
- **¿recall vs MRR?** recall@k = ¿está el dato en el top-k? (cobertura). MRR = ¿qué tan
  arriba? (orden). Híbrido subió recall; rerank subió MRR. Son preguntas distintas.
- **Limitación del eval:** 11 preguntas es chico; ground-truth auto-derivado. Lo ampliaría
  (20-30, multi-página, negativos) y agregaría faithfulness.

## 8. Frontend / sistema
- **¿Cómo funciona el salto a página?** El LLM cita en formato exacto `[página N]`; el front
  lo parsea con regex y lo vuelve botón; el click setea el estado `page` en `App` (lifting
  state up) y el visor (componente **controlado**) re-renderiza esa página.
- **¿Por qué ese formato exacto?** Para parsearlo confiable; desacopla backend (genera texto)
  de frontend (lo vuelve interactivo).
- **¿FastAPI por qué?** ASGI async, validación con Pydantic, OpenAPI autogenerada. `/health`,
  `/ask`, `/pdf`, CORS para dev.

## 9. Bugs reales (mostrar madurez)
- **Batching de embeddings:** mandaba todos los chunks en un request → la API tope a **2048
  inputs**. Lo descubrí en la primera corrida real (los tests eran mockeados). Fix: batchear.
- **`cur.rowcount` con `execute_values`:** reportaba 5 en vez de 2605 (cuenta solo la última
  página interna). Fix: `RETURNING`. *Lección:* los tests mockeados no ven límites reales de
  las APIs; una corrida real es otra capa de test.

## 10. Preguntas "trampa" / meta
- **¿Por qué no LangChain/LlamaIndex?** Para una demo que tengo que **entender y defender**,
  preferí explícito y mínimo. Esos frameworks aceleran pero esconden el retrieval/prompting.
  En un equipo, los evaluaría por velocidad.
- **¿Qué fue lo más difícil?** El recall sobre tablas densas y ruidosas de OCR — me llevó a
  híbrida + rerank, y a medir en vez de adivinar.
- **¿Qué cambiarías / qué falta para producción?** → ver [[13-escalabilidad-y-produccion]].
- **¿Cómo lo extenderías si te pido X?** → ver [[14-extender-el-codigo]].

---

## Cómo estudiar esto
1. Practicá el **pitch** y los temas 4–7 (híbrida, rerank, eval, anti-alucinación) **en voz
   alta** — son el corazón.
2. Sabé **dibujar la arquitectura** (las dos fases) en una hoja.
3. Tené los **números** en la punta de la lengua (recall@5 0.45→0.73→0.91; MRR 0.36→0.39→0.69).
4. Corré la **demo** una vez de punta a punta para que las manos la conozcan.
