"""PDF text extraction via OCR.

The aviation parts catalog is a scanned document that ships with only a partial
OCR layer, so the embedded text is unreliable. Instead of trusting it, we render
each page to an image at a controlled resolution and run a modern OCR engine
(Tesseract) over the rendered image.

OCR of ~600 pages is slow (seconds per page), so the extracted text is cached to
a JSON file (see ``save_extracted_text`` / ``load_extracted_text``). Downstream
steps (chunking, embedding) read the cache and never need to re-run OCR.
"""
import io
import json
import os
import sys
from typing import Optional, TypedDict

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


class ExtractedPage(TypedDict):
    """One OCR'd page. ``page_number`` is 1-based to match how humans cite pages."""

    page_number: int
    text: str


# 200 DPI gives Tesseract enough detail to read small part numbers on these
# scans without blowing up image size (and OCR time). 300 DPI reads slightly
# better at a meaningful speed cost; expose ``dpi`` so it can be tuned per PDF.
DEFAULT_DPI = 200

# PDF user space is 72 units per inch, so the render zoom factor is dpi / 72.
PDF_POINTS_PER_INCH = 72

# Test PDF that already lives in the repo, used as the default in __main__.
# Lives under data/ so it is copied into the Docker image (see Dockerfile).
DEFAULT_PDF_PATH = "data/Cessna 172 Parts Catalog (1963-1974).pdf"


def _check_tesseract_available() -> None:
    """Fail fast with an actionable message if the Tesseract binary is missing.

    Without this, every single page would raise inside the per-page handler and
    we'd silently get ~600 empty pages plus 600 confusing error lines.
    """
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
    """Render a single PDF page to a PIL image at the requested DPI.

    We go through a PNG byte buffer rather than reading ``pixmap.samples``
    directly so the conversion is correct regardless of the page's color space
    or alpha channel. The encode/decode cost is negligible next to OCR.
    """
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
    """Render each page of ``pdf_path`` and OCR it into plain text.

    Args:
        pdf_path: Path to the (scanned) PDF.
        dpi: Render resolution. Higher = better OCR, slower, larger images.
        max_pages: If set, only process the first N pages (handy for quick tests).
        lang: Tesseract language pack(s), e.g. "eng" or "eng+spa".

    Returns:
        One dict per processed page with keys ``page_number`` (1-based int) and
        ``text`` (str). A page whose OCR fails contributes empty text instead of
        aborting the whole run.
    """
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

            # Per-page isolation: one bad page (corrupt image, OCR crash) must not
            # throw away the OCR work already done on the other pages.
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
    """Persist OCR results to JSON so OCR runs at most once per PDF.

    ``ensure_ascii=False`` keeps accented characters readable in the file; the
    indentation makes it easy to eyeball OCR quality while debugging.
    """
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
    # Quick visual check: OCR the first few pages of a PDF and print a preview of
    # each so we can confirm the engine is actually reading the scans.
    # Usage: python -m src.pdf_loader [path/to/file.pdf]
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF_PATH
    preview_chars = 300

    print(f"Extracting first 5 pages of: {pdf_path}\n")
    extracted = extract_pages_from_pdf(pdf_path, max_pages=5)

    for page in extracted:
        text = page["text"]
        print(f"\n===== Page {page['page_number']} ({len(text)} chars) =====")
        print(text[:preview_chars] if text else "<no text extracted>")
