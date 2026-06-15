import { useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { PDF_URL } from '../api';

// PDF.js renders on a web worker; point it at the worker shipped with pdfjs-dist.
// Vite turns this into a proper bundled worker URL.
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

  const clamp = (p: number) => Math.min(Math.max(1, p), numPages ?? p);

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
