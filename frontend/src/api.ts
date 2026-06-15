import type { AskResponse } from './types';

// Backend base URL; override with VITE_API_BASE (see .env.example).
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

// The PDF served by the backend (GET /pdf), consumed by the viewer.
export const PDF_URL = `${API_BASE}/pdf`;

export async function ask(query: string, topK?: number): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK }),
  });

  if (!res.ok) {
    // FastAPI returns {"detail": ...} on errors; surface it when possible.
    let detail = `Request failed (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail);
  }

  return (await res.json()) as AskResponse;
}
