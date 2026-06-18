# Etapa 13 — Escalabilidad y producción

Para responder "¿cómo escala esto?" y "¿qué le falta para producción?". La clave en la
entrevista: **identificar qué se rompe primero** y proponer el fix proporcional, sin
sobre-ingeniería.

---

## A. Escalar los DATOS (670 págs → 100k docs / millones de chunks)

**Qué se rompe primero, en orden:**

1. **Memoria del índice HNSW.** HNSW vive en RAM; con millones de vectores de 1536 dims
   (~6 KB c/u) son GBs. *Fixes:* **quantization** (pgvector soporta `halfvec`/binary →
   menos memoria), bajar dimensiones (`text-embedding-3-small` permite `dimensions=`),
   o **particionar** (sharding por documento/fuente).
2. **Tiempo de build del índice y de los inserts.** HNSW es lento de construir. *Fixes:*
   construir el índice **después** del bulk load; inserts en batch; `maintenance_work_mem`.
3. **Costo y tiempo de embeddings en la ingesta.** Millones de chunks = $ y horas. *Fixes:*
   pipeline batch asíncrono, `embed_texts` ya batchea (≤2048), paralelizar, cachear por hash.
4. **OCR.** Es O(páginas) y caro. *Fixes:* paralelizar por página/worker, cola de trabajos
   (Celery/RQ), persistir el cache en object storage (S3), no re-OCR (idempotente por hash).

**Otras palancas a escala:**
- **IVFFlat o IVFPQ** en vez de HNSW si la memoria aprieta (menos RAM, hay que tunear
  `nlist`/`nprobe`, entrenar).
- **Filtrado con metadata** (`WHERE source=... AND section=...`) para reducir el espacio de
  búsqueda — gratis en Postgres, ventaja de no usar una vector DB pura.
- **Chunking estructural** se vuelve más importante (mejor señal por chunk).

## B. Escalar los USUARIOS (1 → 1000 concurrentes)

**Qué se rompe primero:**

1. **Conexión a Postgres por request.** Hoy `get_db` abre/cierra una conexión por request
   (simple pero no escala). *Fix:* **connection pool** (PgBouncer, o `psycopg_pool`). Es el
   primer cambio que haría — ya está anotado como "próximo paso" en el código.
2. **Workers de la API.** Un uvicorn no alcanza. *Fix:* **gunicorn + uvicorn workers** (N =
   cores), detrás de un reverse proxy (nginx). Escalado horizontal (réplicas) detrás de un LB.
3. **Rate limits de OpenAI** (embeddings + LLM + rerank). A concurrencia alta pegás los
   límites. *Fixes:* **caché de embeddings de queries** y **caché de respuestas** (preguntas
   repetidas), backoff/retries (ya hay), colas, o modelos self-hosted.
4. **Latencia del rerank.** Suma una llamada LLM al camino crítico. *Fixes:* **streaming** de
   la respuesta, cross-encoder local (sin red), o reranking opcional según carga.

**Palancas transversales:** caché (Redis) de queries y embeddings; CDN para el PDF estático;
async donde tenga sentido.

## C. Latencia (perfil de una request)
```
embed query (~tens ms) → vector kNN (HNSW, ms) → full-text (GIN, ms) → RRF (μs)
  → rerank LLM (cientos de ms) → generación LLM (segundos)  ← el grueso
```
El cuello es el LLM. *Fixes:* **streaming de tokens** (mejora *percibida*), prompt más corto
(menos chunks/menos tokens), modelo más rápido, caché de respuestas.

## D. Checklist de producción (lo que HOY falta)

| Área | Hoy | Producción |
|---|---|---|
| **Conexiones DB** | una por request | pool (PgBouncer) |
| **Servidor** | 1 uvicorn (dev) | gunicorn+workers, réplicas, LB |
| **Auth/Authz** | ninguna | API keys / OAuth, por-tenant |
| **Secrets** | `.env` | secret manager (Vault, SSM) |
| **Observabilidad** | prints | logs estructurados, métricas (latencia, recall), tracing, **tracking de costo** por request |
| **Rate limiting** | ninguno | por usuario/IP |
| **Errores/resiliencia** | try/except básico | retries/backoff (hay algo), circuit breaker, timeouts |
| **CI/CD** | CI corre tests | + lint, build de imagen, deploy, **eval en CI** (anti-regresión de recall) |
| **Deploy** | docker-compose | contenedores en k8s/ECS, IaC |
| **DB ops** | volumen local | backups, migraciones versionadas (Alembic), réplicas |
| **Seguridad** | — | **prompt injection** (el doc es input no confiable), PII, sanitización, límites de tamaño |
| **Datos** | re-ingest manual | pipeline versionado, re-OCR incremental, detección de cambios |

## E. Seguridad específica de RAG (punto fuerte si lo mencionás)
- **Prompt injection vía documento:** el catálogo es input no confiable; un PDF malicioso
  podría intentar inyectar instrucciones. Mitigaciones: el contexto va en un bloque delimitado,
  el system prompt manda, y no se ejecutan acciones desde el texto recuperado.
- **Fuga de datos / multi-tenant:** filtrar por `tenant_id` en el retrieval; nunca mezclar
  corpus entre clientes.
- **PII / compliance:** según el dominio, redactar o controlar qué se manda al LLM externo.

## F. Cómo lo plantearía (frase para la entrevista)
> "Para *esta* escala (un catálogo, demo) elegí lo simple y correcto: Postgres único,
> conexión por request, un uvicorn. El **primer** cambio para producción sería el **pool de
> conexiones** y **workers**; después **observabilidad con tracking de costo** y **eval en
> CI** para no regresionar el recall. La arquitectura ya deja la puerta abierta: Postgres
> escala con quantization/particiones, y el retrieval es modular (puedo swappear el reranker
> o sumar caché sin tocar el resto)."

## Conceptos clave (para la entrevista)
- **"Qué se rompe primero"** > lista genérica: muestra criterio de ingeniería.
- **Fix proporcional**: no sobre-ingeniería para una demo; saber *cuándo* haría cada cosa.
- **Costo como métrica de primer nivel** en sistemas con LLM.
