import { Suspense, lazy, useState } from 'react';
import { AskPanel } from './components/AskPanel';
import './App.css';

// Lazy-load the viewer so the heavy PDF.js bundle is a separate chunk, fetched
// only when the app mounts the viewer (keeps the initial JS payload smaller).
const PdfViewer = lazy(() =>
  import('./components/PdfViewer').then((m) => ({ default: m.PdfViewer })),
);

export default function App() {
  const [page, setPage] = useState(1);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Aviation Parts RAG</h1>
        <p>Ask questions about the Cessna 172 parts catalog.</p>
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
