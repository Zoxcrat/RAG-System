import { useState } from 'react';
import { PdfViewer } from './components/PdfViewer';
import { AskPanel } from './components/AskPanel';
import './App.css';

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
          <PdfViewer page={page} onPageChange={setPage} />
        </section>
        <section className="qa-pane">
          <AskPanel onPagesFound={(pages) => pages[0] && setPage(pages[0])} />
        </section>
      </main>
    </div>
  );
}
