import { useState, type FormEvent } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { PDF_URL } from '../api';

// Point PDF.js at the bundled worker.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface Props {
  page: number;
  onPageChange: (page: number) => void;
}

export function PdfViewer({ page, onPageChange }: Props) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [goto, setGoto] = useState('');

  const clamp = (p: number) => Math.min(Math.max(1, p), numPages ?? p);

  function handleGoto(e: FormEvent) {
    e.preventDefault();
    const n = parseInt(goto, 10);
    if (!Number.isNaN(n)) onPageChange(clamp(n));
    setGoto('');
  }

  return (
    <div className="pdf-viewer">
      <div className="pdf-toolbar">
        <button onClick={() => onPageChange(clamp(page - 1))} disabled={page <= 1}>
          ‹ Prev
        </button>
        <span className="pdf-page-label">
          Page {page}
          {numPages ? ` / ${numPages}` : ''}
        </span>
        <button
          onClick={() => onPageChange(clamp(page + 1))}
          disabled={numPages != null && page >= numPages}
        >
          Next ›
        </button>
        <form className="pdf-goto" onSubmit={handleGoto}>
          <input
            type="number"
            min={1}
            max={numPages ?? undefined}
            value={goto}
            onChange={(e) => setGoto(e.target.value)}
            placeholder="Go to…"
            aria-label="Go to page"
          />
        </form>
      </div>

      <div className="pdf-canvas">
        <Document
          file={PDF_URL}
          onLoadSuccess={({ numPages }) => setNumPages(numPages)}
          loading={<div className="pdf-status">Loading PDF…</div>}
          error={<div className="pdf-status">Could not load the PDF.</div>}
        >
          <Page
            pageNumber={page}
            width={620}
            renderTextLayer
            renderAnnotationLayer={false}
          />
        </Document>
      </div>
    </div>
  );
}
