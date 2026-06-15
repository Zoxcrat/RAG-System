import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server on :5173; the FastAPI backend runs separately on :8000 (CORS-enabled).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
