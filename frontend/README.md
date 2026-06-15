# Frontend — Aviation Parts RAG

React + Vite + TypeScript SPA. Renders the PDF (via PDF.js / `react-pdf`) and a
Q&A panel that talks to the FastAPI backend.

## Run (dev)

```bash
# 1) start the backend first (from the repo root): make up && make api
# 2) then, here:
npm install
npm run dev          # http://localhost:5173
```

Configure the backend URL with `VITE_API_BASE` (see `.env.example`); defaults to
`http://localhost:8000`.

## Build

```bash
npm run build        # tsc type-check + vite production build into dist/
```
