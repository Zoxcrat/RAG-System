# Etapa 5 — Frontend React + visor PDF

## Qué se construyó
Una app separada en `frontend/` (Vite + React + TypeScript) que **renderiza el
PDF** y un **panel de Q&A** conectado a la API. Continúa [[04-api-fastapi]].

## Stack y por qué
- **Vite + React + TypeScript.** Vite da un build y un dev server rápidos (CRA
  está deprecado). TypeScript es coherente con los type hints del backend y
  documenta el contrato con la API.
- **react-pdf** (wrapper de **PDF.js**). Renderiza el PDF en el browser y deja
  **controlar qué página se muestra**, que es lo que necesita la Etapa 6.

## Estructura
```
frontend/src/
  api.ts                 cliente: POST /ask, URL de GET /pdf
  types.ts               espejo del contrato AskResponse/Source
  components/
    PdfViewer.tsx        <Document>/<Page> + navegación prev/next
    AskPanel.tsx         input, submit, respuesta, fuentes, loading/error
  App.tsx                layout (visor izq. / Q&A der.) + estado `page`
```

## Decisiones técnicas y por qué
- **Lifting state up (el estado `page` vive en `App`).** El visor y el panel
  comparten la página actual. Así, cuando llega una respuesta, el visor puede
  **saltar** a la página fuente (por ahora a la primera). En la **Etapa 6**, cada
  cita `[página N]` va a setear ese `page` → es el cimiento del feature estrella.
- **Worker de PDF.js.** PDF.js corre su parsing en un **web worker** (no bloquea
  el hilo de UI). Lo apuntamos al worker que trae `pdfjs-dist` con
  `new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url)`, que Vite
  empaqueta como un asset real.
- **Una página a la vez** (`<Page pageNumber={page} />`) + navegación. Simple y
  perfecto para "saltar a una página".
- **Cliente de API tipado** con manejo de errores: si el backend responde un
  error, lee el `detail` de FastAPI y lo muestra.
- **`VITE_API_BASE`** configurable (default `http://localhost:8000`).

## Cómo correr (dev)
```bash
# backend (repo root)
make up && make api          # Postgres + API en :8000
# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```
El backend ya tiene CORS habilitado. `POST /ask` real necesita `OPENAI_API_KEY`.

## Estado / pendiente
- ✅ **Build verificado** (`npm run build`: `tsc` + `vite build` compilan y tipan).
- ⏳ Render visual y Q&A en vivo: con `npm run dev` + backend con API key.
- ⚠️ `npm audit` reporta 3 vulnerabilidades (deps de pdfjs) y el bundle de pdfjs
  es grande → revisar/code-split en la **Etapa 7**.
- **Próximo (Etapa 6):** parsear `[página N]` del `answer` y renderizar cada cita
  como un **botón que salta el visor** a esa página.

## Conceptos clave (para la entrevista)
- **SPA + bundler (Vite):** módulos ES, dev server con HMR, build de producción.
- **Web worker de PDF.js:** por qué el parsing del PDF va fuera del hilo de UI.
- **Lifting state up:** compartir estado entre componentes hermanos subiéndolo al
  ancestro común — la pieza que conecta Q&A ↔ visor.
