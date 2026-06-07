"""
PDF text extraction module using PyMuPDF (fitz).
"""

import fitz  # PyMuPDF


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract all text content from a PDF file.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        A string containing the concatenated text of every page,
        separated by page-break markers.
    """
    doc = fitz.open(pdf_path)
    pages: list[str] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        pages.append(f"--- Page {page_num + 1} ---\n{text}")

    doc.close()
    return "\n\n".join(pages)


def get_pdf_metadata(pdf_path: str) -> dict:
    """
    Return basic metadata about the PDF (title, author, page count, etc.).

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        A dict with keys: title, author, subject, page_count.
    """
    doc = fitz.open(pdf_path)
    metadata = doc.metadata or {}

    info = {
        "title": metadata.get("title", "N/A"),
        "author": metadata.get("author", "N/A"),
        "subject": metadata.get("subject", "N/A"),
        "page_count": len(doc),
    }

    doc.close()
    return info
