import { Suspense, lazy, useState } from 'react';
import { AskPanel } from './components/AskPanel';
import './App.css';

// Lazy-load so PDF.js lands in its own chunk.
const PdfViewer = lazy(() =>
  import('./components/PdfViewer').then((m) => ({ default: m.PdfViewer })),
);

export default function App() {
  const [page, setPage] = useState(1);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">✈</span>
          <div>
            <h1>Aviation Parts RAG</h1>
            <p>Cessna 172 parts catalog · ask &amp; jump to the exact page</p>
          </div>
        </div>
        <span className="brand-badge">
          <span className="dot" aria-hidden="true" />
          Hybrid search + reranking
        </span>
      </header>

      <main className="app-main">
        <section className="viewer-pane">
          <Suspense fallback={<div className="pdf-status">Loading viewer…</div>}>
            <PdfViewer page={page} onPageChange={setPage} />
          </Suspense>
        </section>
        <section className="qa-pane">
          <AskPanel onGoToPage={setPage} currentPage={page} />
        </section>
      </main>
    </div>
  );
}
