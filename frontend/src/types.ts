// Mirrors the FastAPI /ask response (src/api.py: AskResponse / Source).
export interface Source {
  id: number;
  source: string | null;
  chunk_index: number | null;
  page_number: number | null;
  distance: number | null;
}

export interface AskResponse {
  query: string;
  answer: string;
  sources: Source[];
  pages: number[];
  min_distance: number | null;
  // "lookup" (semantic) or "aggregate" (structured); sql is shown for transparency.
  mode?: string;
  sql?: string | null;
}
