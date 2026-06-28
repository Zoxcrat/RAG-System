"""PDF text extraction via Tesseract OCR, cached to JSON to avoid re-running."""
import io
import json
import os
import sys
from typing import Optional, TypedDict

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


class ExtractedPage(TypedDict):
    """One OCR'd page; page_number is 1-based."""

    page_number: int
    text: str


# Enough detail to read small part numbers without blowing up OCR time.
DEFAULT_DPI = 200

# PDF user space is 72 units per inch; zoom = dpi / 72.
PDF_POINTS_PER_INCH = 72

DEFAULT_PDF_PATH = "data/Cessna 172 Parts Catalog (1963-1974).pdf"


def _check_tesseract_available() -> None:
    """Fail fast with an install hint if the Tesseract binary is missing."""
    try:
        pytesseract.get_tesseract_version()
    except (pytesseract.TesseractNotFoundError, EnvironmentError) as exc:
        raise RuntimeError(
            "Tesseract OCR engine not found on this system. Install it first:\n"
            "  Linux (Debian/Ubuntu): sudo apt-get install -y tesseract-ocr\n"
            "  macOS (Homebrew):      brew install tesseract\n"
            f"Original error: {exc}"
        ) from exc


def _render_page_to_image(page: "fitz.Page", dpi: int) -> Image.Image:
    """Render a PDF page to a PIL image at the requested DPI."""
    zoom = dpi / PDF_POINTS_PER_INCH
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix)
    return Image.open(io.BytesIO(pixmap.tobytes("png")))


def extract_pages_from_pdf(
    pdf_path: str,
    dpi: int = DEFAULT_DPI,
    max_pages: Optional[int] = None,
    lang: str = "eng",
) -> list[ExtractedPage]:
    """Render each page of ``pdf_path`` and OCR it into plain text; a failed page yields empty text."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    _check_tesseract_available()

    pages: list[ExtractedPage] = []
    with fitz.open(pdf_path) as doc:
        total_pages = doc.page_count
        num_pages = total_pages if max_pages is None else min(max_pages, total_pages)

        for page_index in range(num_pages):
            page_number = page_index + 1
            print(f"Processing page {page_number}/{num_pages}...")

            try:
                image = _render_page_to_image(doc[page_index], dpi)
                text = pytesseract.image_to_string(image, lang=lang).strip()
            except Exception as exc:  # noqa: BLE001 - log and continue, never abort
                print(
                    f"  OCR failed on page {page_number}: {exc}",
                    file=sys.stderr,
                )
                text = ""

            pages.append({"page_number": page_number, "text": text})

    return pages


def save_extracted_text(pages: list[ExtractedPage], output_path: str) -> None:
    """Persist OCR results to JSON so OCR runs at most once per PDF."""
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)


def load_extracted_text(input_path: str) -> list[ExtractedPage]:
    """Load OCR results previously written by ``save_extracted_text``."""
    with open(input_path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Usage: python -m src.ingestion.pdf_loader [path/to/file.pdf]
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF_PATH
    preview_chars = 300

    print(f"Extracting first 5 pages of: {pdf_path}\n")
    extracted = extract_pages_from_pdf(pdf_path, max_pages=5)

    for page in extracted:
        text = page["text"]
        print(f"\n===== Page {page['page_number']} ({len(text)} chars) =====")
        print(text[:preview_chars] if text else "<no text extracted>")
