import { useState, type FormEvent, type KeyboardEvent } from 'react';
import { ask } from '../api';
import { parseAnswer } from '../citations';
import { AnswerText } from './AnswerText';
import type { AskResponse } from '../types';

interface Props {
  onGoToPage: (page: number) => void;
  currentPage: number;
}

const EXAMPLE_QUERIES = [
  'What is the part number for the headliner hanger?',
  'Where is the dorsal assembly listed?',
  'What is part number 0411680?',
];

export function AskPanel({ onGoToPage, currentPage }: Props) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitQuery(override?: string) {
    const q = (override ?? query).trim();
    if (!q || loading) return;
    if (override !== undefined) setQuery(override);

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

      {loading && (
        <div className="loading">
          <span className="spinner" aria-hidden="true" />
          Searching the catalog…
        </div>
      )}
      {error && <div className="error">{error}</div>}
      {!result && !error && !loading && (
        <div className="empty-state">
          <div className="empty-icon" aria-hidden="true">🔍</div>
          <p className="hint">Ask a question about the catalog, or try one:</p>
          <div className="examples">
            <span className="examples-label">Examples</span>
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                type="button"
                className="example-chip"
                onClick={() => void submitQuery(q)}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {result && (
        <div className="answer">
          <h3>Answer</h3>
          <AnswerText answer={result.answer} onCite={onGoToPage} activePage={currentPage} />

          {result.sql && (
            <details className="agg-sql">
              <summary>Answered from the parts table · show SQL</summary>
              <pre>{result.sql}</pre>
            </details>
          )}

          {result.pages.length > 0 && (
            <div className="pages">
              <span className="pages-label">Pages</span>
              {result.pages.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={p === currentPage ? 'page-chip active' : 'page-chip'}
                  onClick={() => onGoToPage(p)}
                  title={`Go to page ${p}`}
                >
                  {p}
                </button>
              ))}
            </div>
          )}

          {result.sources.length > 0 && (
            <div className="sources">
              <h4>Sources</h4>
              <ul>
                {result.sources.map((s) => (
                  <li key={s.id}>
                    <span className="source-page">p. {s.page_number ?? 'n/a'}</span>
                    <span className="source-name">{s.source ?? 'unknown'}</span>
                    {s.distance != null && (
                      <span className="source-dist">{s.distance.toFixed(3)}</span>
                    )}
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
