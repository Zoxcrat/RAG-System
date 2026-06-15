import { useState, type FormEvent } from 'react';
import { ask } from '../api';
import { parseAnswer } from '../citations';
import { AnswerText } from './AnswerText';
import type { AskResponse } from '../types';

interface Props {
  // Jump the PDF viewer to a page (used by the initial answer and citation clicks).
  onGoToPage: (page: number) => void;
}

export function AskPanel({ onGoToPage }: Props) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
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

  return (
    <div className="ask-panel">
      <form onSubmit={handleSubmit} className="ask-form">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask about the parts catalog…"
          rows={3}
        />
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? 'Asking…' : 'Ask'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {result && (
        <div className="answer">
          <h3>Answer</h3>
          <AnswerText answer={result.answer} onCite={onGoToPage} />

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
