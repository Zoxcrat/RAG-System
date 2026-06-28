import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server on :5173; proxy API calls to the backend on :8000 so dev matches
// the same-origin production setup (the API serves the build).
const target = 'http://localhost:8000';
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/ask': target,
      '/pdf': target,
      '/health': target,
    },
  },
});
