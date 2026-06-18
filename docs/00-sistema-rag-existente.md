# Sistema RAG existente (lo construido antes del pipeline de PDF)

Resumen en español del sistema que ya estaba hecho, pensado para estudiarlo de
cara a la entrevista. La fuente canónica y más detallada son `README.md` y
`SPEC.md` (en la raíz, en inglés); este documento condensa el "qué" y, sobre
todo, el **por qué** de cada decisión.

## Qué es
Un pipeline RAG (Retrieval-Augmented Generation) end-to-end, mínimo pero
completo: ingiere documentos de texto plano, guarda sus *embeddings* en
PostgreSQL + PGVector, y responde preguntas recuperando los fragmentos más
relevantes y pidiéndole a un LLM que conteste **usando solo ese contexto**, con
citas y sin inventar cuando no hay información.

## Arquitectura en dos fases

**Ingesta (offline, una vez por corpus):**
```
texto → chunking con overlap → embeddings (batch) → INSERT idempotente en Postgres
```

**Query (online, por pregunta):**
```
pregunta → embedding → búsqueda kNN por distancia coseno (HNSW) → top-k chunks
        → gate de relevancia (si el más cercano está muy lejos → no llama al LLM)
        → prompt "grounded" (contexto + chunks numerados) → LLM → respuesta con citas [n]
```

Dependencias entre módulos (sin ciclos):
```
main ─► rag ─► retrieve ─► embed ─► (OpenAI)
  │      │         │
  │      └─────────┴─► db ─► (PostgreSQL + PGVector)
  └────► ingest ─► embed, db
db, embed, ingest, rag ─► config ─► (.env / entorno)
```

## Módulos (`src/`) y su responsabilidad
| Módulo | Responsabilidad |
|---|---|
| `config` | Única fuente de configuración; el único que lee `os.getenv`. |
| `db` | Conexión y esquema (extensión `vector`, tabla `documents`, índice HNSW, índice único `content_hash`). |
| `embed` | Texto → vectores vía OpenAI (único punto que llama al endpoint de embeddings). |
| `ingest` | Pipeline offline: leer → `chunk_text` (ventana con overlap) → embeddings batch → INSERT. |
| `retrieve` | Embeber la query → kNN por coseno en PGVector → chunks con metadata y distancia. |
| `rag` | Fase de query: arma el prompt grounded, aplica el gate de relevancia, llama al LLM, ensambla la respuesta. |
| `main` | CLI interactiva (capa de presentación). |

## Modelo de datos (tabla `documents`)
`id` (PK), `content` (texto del chunk), `source` (doc origen), `chunk_index`
(posición), `page_number` (página de origen; NULL para texto plano — agregado en
la Etapa 2, ver [[02-ingestion-con-pagina]]), `content_hash` (SHA-256 de
`source + page_number + content`, **único**), `embedding` (`vector(1536)`),
`created_at`. Índices: **HNSW** sobre `embedding` con `vector_cosine_ops` y
**UNIQUE** sobre `content_hash`.

## Decisiones técnicas y por qué (lo importante para la entrevista)
- **PostgreSQL + PGVector en vez de una vector DB dedicada.** Un solo sistema
  guarda vectores + texto + metadata, con SQL y transacciones reales y sin
  piezas extra. Correcto a esta escala y deja la puerta abierta a combinar
  búsqueda vectorial con filtros `WHERE` (búsqueda híbrida) más adelante.
- **HNSW + coseno.** HNSW da kNN aproximado rápido y con buen recall (a costa de
  más memoria e inserts más lentos: buen trade para una carga read-heavy). El
  coseno compara **dirección**, no magnitud — lo estándar para embeddings de
  texto. Rango de distancia: 0 (idéntico) a 2 (opuesto).
- **Chunking por ventana de caracteres (500, overlap 100).** Chunks chicos →
  recuperación precisa; el overlap evita perder una idea que cae justo en el
  borde. Simplicidad deliberada. *Trade-off:* no respeta la estructura del
  documento (mejorable con chunking semántico/estructural).
- **Ingesta idempotente.** Cada chunk se guarda con `content_hash` bajo índice
  único y los inserts usan `ON CONFLICT DO NOTHING`; re-ingerir el mismo
  documento no duplica nada. Los inserts van en **batch** (`execute_values`), no
  uno por uno.
- **Gate de relevancia (umbral 0.5 sobre la distancia mínima).** Un retriever
  siempre devuelve *algo*. Si el chunk más cercano está más lejos que el umbral,
  el sistema **no llama al LLM** y responde honestamente "no tengo información
  suficiente" (con la mejor distancia, útil para tunear). Así una pregunta fuera
  de dominio no produce una respuesta inventada con seguridad.
- **`temperature = 0`.** Respuestas deterministas y fieles al contexto, no
  creativas. Auditable y testeable.
- **Configuración centralizada.** `config.py` es el único que lee el entorno; sus
  defaults coinciden con `docker-compose.yml`, así la app conecta out-of-the-box.
  El cliente de OpenAI se crea con reintentos y timeout para que un error
  transitorio no tumbe un request.
- **Prompt "grounded".** Los chunks van dentro de un bloque `<context>`,
  numerados `[1..k]`. El system prompt obliga a responder solo con ese contexto,
  citar los chunks usados, admitir cuando falta info y no inventar.

## Cómo correrlo (resumen)
Necesitás Docker y una `OPENAI_API_KEY` en `.env` (`cp .env.example .env`).
- **Docker (recomendado, sin Python local):** `make docker-up` y luego
  `make docker-ask`.
- **Local (dev + tests):** `make install-dev`, `make ingest`, `make ask`,
  `make test`. `make help` lista todo. Detalle completo en `README.md`.

## Tests y CI
Suite **totalmente mockeada** (sin DB ni llamadas a la API): cubre la matemática
del chunking, el gate de relevancia (incluido el caso borde del umbral) y la
forma de los resultados de `retrieve`. GitHub Actions la corre en cada push y PR
(`.github/workflows/ci.yml`).

## Notas de infraestructura
El proyecto vive en una carpeta sincronizada por iCloud, **poco fiable para
bind-mount** en Docker. Por eso el **código se hornea en la imagen** (no se
montra) y los datos de Postgres viven en un **named volume** gestionado por
Docker, nunca en la ruta sincronizada. Esta misma política guía el pipeline de
PDF: Tesseract y el PDF van **dentro de la imagen** en vez de depender de la Mac
(ver [[01-extraccion-pdf-ocr]]).

## Relación con la nueva feature
El pipeline de PDF/OCR ([[01-extraccion-pdf-ocr]]) es una **nueva etapa de
ingesta** para documentos escaneados: produce texto por página que después
alimentará el chunking + embeddings ya existentes (reutilizando `ingest`,
`embed` y `db`).

## Roadmap del proyecto (lo que pediría una versión productiva)
Búsqueda híbrida (vector + keyword/BM25), chunking estructural (por secciones y
tablas), reranking con cross-encoder, evaluación (recall@k, MRR, fidelidad) y
streaming de tokens.
