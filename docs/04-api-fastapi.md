# Etapa 4 — Backend API REST (FastAPI)

## Qué se construyó
`src/api.py`: expone el pipeline RAG por **HTTP**, para que el navegador (el
frontend de la Etapa 5) pueda consumirlo. Continúa [[03-retrieval-citas-pagina]].

## Endpoints
| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/health` | Liveness: `{"status": "ok"}`. No toca la DB. |
| `POST` | `/ask` | `{query, top_k?}` → `{query, answer, sources[…page_number], pages, min_distance}`. |
| `GET` | `/pdf` | Sirve el PDF (`application/pdf`) para el visor. |

## Teoría (para la entrevista)
- **FastAPI es un framework ASGI** (asíncrono). Define la API con **type hints**:
  los modelos **Pydantic** validan automáticamente el request y serializan el
  response, y de paso FastAPI **genera la documentación OpenAPI/Swagger sola**
  (en `http://localhost:8000/docs`).
- **Contrato tipado:** `AskRequest`/`AskResponse` son el contrato explícito entre
  back y front. Si el request no cumple (p. ej. `query` vacío, `top_k <= 0`),
  FastAPI responde **422** sin que escribamos validación a mano.
- **CORS (Cross-Origin Resource Sharing):** el navegador bloquea por seguridad
  los pedidos a un origen distinto del de la página. En dev el front corre en
  otro puerto que la API, así que hay que **permitir el origen explícitamente**
  (middleware de CORS).
- **Por qué servir el PDF desde el backend:** el visor (PDF.js) necesita los
  **bytes** del PDF; `GET /pdf` se los entrega con `FileResponse`.

## Decisiones técnicas y por qué
- **Conexión a Postgres por request** (dependency `get_db` con `yield`: abre,
  cede, cierra en `finally`). Es simple y correcto; las conexiones de `psycopg2`
  no se comparten entre threads. *Próximo paso para producción:* un **pool** de
  conexiones (las requests sync de FastAPI corren en un threadpool).
- **`response_model=AskResponse`:** FastAPI valida/serializa la salida contra el
  modelo → contrato garantizado y documentado.
- **Manejo de errores explícito:** `query` vacío/whitespace → 422; un fallo
  interno (DB, etc.) se traduce a un **500 con JSON** legible, no a un stack trace.
- **`PDF_PATH` y `CORS_ORIGINS` en `config.py`** (config centralizada,
  configurable por variables de entorno).
- **Reuso de la imagen Docker:** el servicio `api` usa **la misma imagen** que la
  CLI; solo cambia el `command` a `uvicorn`. El `entrypoint` inicializa el schema
  igual antes de arrancar.

## Cómo se usa
- **Local:** `make up` (Postgres) y luego `make api` (uvicorn con `--reload`).
  Documentación interactiva en `http://localhost:8000/docs`.
- **Docker:** `make docker-api` (levanta Postgres + API en `:8000`).
- `/health` y `/pdf` funcionan sin API key; **`/ask` real necesita
  `OPENAI_API_KEY`** (embeddings + LLM).

## Estado / pendiente
- ✅ **40 tests passing** (8 de API con `TestClient`, mockeados, sin DB ni key).
- ⏳ `/ask` end-to-end pendiente (necesita `OPENAI_API_KEY`).
- **Próximo (Etapa 5):** frontend React + visor PDF.js que consume `POST /ask`
  y `GET /pdf`.

## Conceptos clave (para la entrevista)
- **ASGI vs WSGI** (asíncrono vs sincrónico).
- **Validación declarativa + OpenAPI autogenerada** con Pydantic.
- **CORS** y por qué aparece en apps front+back separadas.
