import { useState, type FormEvent, type KeyboardEvent } from 'react';
import { ask } from '../api';
import { parseAnswer } from '../citations';
import { AnswerText } from './AnswerText';
import type { AskResponse } from '../types';

interface Props {
  onGoToPage: (page: number) => void;
  currentPage: number;
}

export function AskPanel({ onGoToPage, currentPage }: Props) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitQuery() {
    const q = query.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    try {
      const res = await ask(q);
      setResult(res);
      // Jump to the first page the answer actually cites, if any.
      const firstCitation = parseAnswer(res.answer).find((s) => s.type === 'citation');
      if (firstCitation?.type === 'citation') onGoToPage(firstCitation.page);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    void submitQuery();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Cmd/Ctrl+Enter submits; plain Enter keeps inserting newlines.
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void submitQuery();
    }
  }

  return (
    <div className="ask-panel">
      <form onSubmit={handleSubmit} className="ask-form">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the parts catalog…"
          rows={3}
        />
        <div className="ask-actions">
          <button type="submit" disabled={loading || !query.trim()}>
            {loading ? 'Asking…' : 'Ask'}
          </button>
          <span className="hint-inline">⌘/Ctrl + Enter</span>
        </div>
      </form>

      {loading && <div className="loading">Searching the catalog…</div>}
      {error && <div className="error">{error}</div>}
      {!result && !error && !loading && (
        <p className="hint">Ask a question about the catalog to get started.</p>
      )}

      {result && (
        <div className="answer">
          <h3>Answer</h3>
          <AnswerText answer={result.answer} onCite={onGoToPage} activePage={currentPage} />

          {result.pages.length > 0 && (
            <p className="pages">Pages: {result.pages.join(', ')}</p>
          )}

          {result.sources.length > 0 && (
            <div className="sources">
              <h4>Sources</h4>
              <ul>
                {result.sources.map((s) => (
                  <li key={s.id}>
                    {s.source ?? 'unknown'} — page {s.page_number ?? 'n/a'}
                    {s.distance != null && ` · distance ${s.distance.toFixed(3)}`}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
