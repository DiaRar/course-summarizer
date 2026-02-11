import fitz
import pymupdf4llm
from pathlib import Path
from typing import List, Tuple
import re

ICON_FONTS = {"Wingdings", "Wingdings2", "Wingdings3", "Symbol", "ZapfDingbats"}

# ---------------------------------------------------------------------------
# Strategy 1: pymupdf4llm (best for digitally native PDFs)
# ---------------------------------------------------------------------------

def _extract_via_pymupdf4llm(pdf_path: Path) -> List[Tuple[str, str]]:
    """
    Uses pymupdf4llm for high-quality markdown extraction.
    Works best on native PDFs with proper text layers.
    """
    pages = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    slides = []
    for i, page in enumerate(pages):
        md = page.get("text", "").strip()
        if not md:
            slides.append((f"Slide {i + 1}", ""))
            continue
        
        # Split into title + body from first heading or first line
        lines = md.split("\n", 1)
        title = lines[0].lstrip("#").strip() or f"Slide {i + 1}"
        body = lines[1].strip() if len(lines) > 1 else ""
        slides.append((title, body))
    return slides


# ---------------------------------------------------------------------------
# Strategy 2: fitz dict mode (fallback for PPTX-converted / image-heavy PDFs)
# ---------------------------------------------------------------------------

def _is_icon_span(span: dict) -> bool:
    font = span.get("font", "")
    return any(icon in font for icon in ICON_FONTS)


def _extract_page_fitz(page) -> Tuple[str, str]:
    """Font-size-aware extraction from a single page."""
    d = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

    spans_data = []
    for bi, block in enumerate(d.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for li, line in enumerate(block.get("lines", [])):
            for si, span in enumerate(line.get("spans", [])):
                text = span.get("text", "").strip()
                if not text:
                    continue
                spans_data.append({
                    "block": bi, "line": li, "span": si,
                    "size": span.get("size", 12),
                    "text": text,
                    "is_icon": _is_icon_span(span),
                })

    if not spans_data:
        return (f"Slide {page.number + 1}", "")

    content_spans = [
        s for s in spans_data
        if not s["is_icon"] and not (re.match(r"^\d{1,3}$", s["text"]) and s["size"] < 20)
    ]
    if not content_spans:
        return (f"Slide {page.number + 1}", "")

    max_size = max(s["size"] for s in content_spans)
    title_threshold = max_size - 2
    title_parts, body_lines_by_block, title_block = [], {}, None

    for s in content_spans:
        if s["size"] >= title_threshold and title_block is None:
            title_block = s["block"]
        if s["size"] >= title_threshold and s["block"] == title_block:
            title_parts.append(s)
        else:
            bkey = s["block"]
            if bkey not in body_lines_by_block:
                body_lines_by_block[bkey] = []
            line_key = (s["block"], s["line"])
            if body_lines_by_block[bkey] and body_lines_by_block[bkey][-1]["_key"] == line_key:
                body_lines_by_block[bkey][-1]["text"] += " " + s["text"]
            else:
                body_lines_by_block[bkey].append({"text": s["text"], "_key": line_key})

    title = " ".join(s["text"] for s in title_parts).strip() or f"Slide {page.number + 1}"

    paragraphs = []
    for bkey in sorted(body_lines_by_block.keys()):
        merged = []
        for line_data in body_lines_by_block[bkey]:
            text = line_data["text"].strip()
            if not text:
                continue
            if merged and not re.search(r"[.!?:;,\)\]\}]$", merged[-1]):
                merged[-1] += " " + text
            else:
                merged.append(text)
        if merged:
            paragraphs.append("\n".join(merged))

    body = "\n\n".join(paragraphs)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return (title, body)


def _extract_via_fitz(pdf_path: Path) -> List[Tuple[str, str]]:
    """Font-size-aware fitz extraction for all pages."""
    doc = fitz.open(pdf_path)
    return [_extract_page_fitz(page) for page in doc]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

MIN_CHARS_PER_PAGE = 30  # threshold to detect sparse pymupdf4llm output


def extract_text_from_pdf(pdf_path: Path) -> List[Tuple[str, str]]:
    """
    Extracts text from a PDF. Tries pymupdf4llm first (best for native PDFs),
    falls back to font-aware fitz extraction if output is too sparse
    (e.g. PPTX-converted PDFs).
    """
    slides = _extract_via_pymupdf4llm(pdf_path)

    # Check if pymupdf4llm produced meaningful content
    total_chars = sum(len(t) + len(b) for t, b in slides)
    avg_chars = total_chars / max(len(slides), 1)

    if avg_chars >= MIN_CHARS_PER_PAGE:
        return slides

    # Fallback to fitz dict extraction
    return _extract_via_fitz(pdf_path)


def write_slides_md(slides: List[Tuple[str, str]], out_path: Path):
    """Writes extracted slides to markdown format."""
    with open(out_path, "w", encoding="utf-8") as f:
        for title, body in slides:
            f.write(f"# {title}\n\n")
            f.write(f"{body}\n\n")
            f.write("---\n\n")
