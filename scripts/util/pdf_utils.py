import fitz
import pymupdf4llm
from pathlib import Path
from typing import List, Tuple
import re

ICON_FONTS = {"Wingdings", "Wingdings2", "Wingdings3", "Symbol", "ZapfDingbats"}

# Presentation tools that produce PDFs better handled by fitz dict mode
_PRESENTATION_CREATORS = {
    "impress", "powerpoint", "keynote", "google slides",
    "libreoffice", "openoffice",
}


# ---------------------------------------------------------------------------
# Pre-flight: inspect the PDF to pick a strategy *before* extraction
# ---------------------------------------------------------------------------

def _is_presentation_origin(doc: fitz.Document) -> bool:
    """Check PDF metadata for presentation-tool creators."""
    meta = doc.metadata or {}
    creator = (meta.get("creator") or "").lower()
    producer = (meta.get("producer") or "").lower()
    for tag in _PRESENTATION_CREATORS:
        if tag in creator or tag in producer:
            return True
    return False


def _image_block_ratio(doc: fitz.Document, sample_pages: int = 5) -> float:
    """
    Return the fraction of blocks that are images across a sample of pages.
    A high ratio (> 0.4) suggests scanned or PPTX-converted content.
    """
    total_blocks = 0
    image_blocks = 0
    pages_to_check = min(len(doc), sample_pages)
    for i in range(pages_to_check):
        blocks = doc[i].get_text("dict", flags=0).get("blocks", [])
        for b in blocks:
            total_blocks += 1
            if b.get("type") == 1:          # image block
                image_blocks += 1
    if total_blocks == 0:
        return 0.0
    return image_blocks / total_blocks


def _has_uniform_page_size(doc: fitz.Document) -> bool:
    """
    Slides from presentations almost always have identical page dimensions.
    If every page has the same size, it's likely a slide deck.
    """
    if len(doc) < 2:
        return False
    first = (round(doc[0].rect.width), round(doc[0].rect.height))
    return all(
        (round(p.rect.width), round(p.rect.height)) == first
        for p in doc
    )


def _is_landscape(doc: fitz.Document) -> bool:
    """Landscape orientation is a strong slide-deck signal."""
    if len(doc) == 0:
        return False
    r = doc[0].rect
    return r.width > r.height


# ---------------------------------------------------------------------------
# Quality scoring for pymupdf4llm output
# ---------------------------------------------------------------------------

_MIN_CHARS_PER_PAGE = 30

def _score_md_quality(pages_md: list) -> float:
    """
    Score 0-1 for how well-structured the pymupdf4llm markdown output is.
    Checks: heading presence, average line length, ratio of non-empty pages.
    """
    if not pages_md:
        return 0.0

    n = len(pages_md)
    heading_count = 0
    nonempty_count = 0
    total_line_len = 0
    total_lines = 0

    for page in pages_md:
        md = page.get("text", "").strip()
        if not md:
            continue
        nonempty_count += 1
        lines = md.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            total_lines += 1
            total_line_len += len(stripped)
            if stripped.startswith("#"):
                heading_count += 1

    if total_lines == 0:
        return 0.0

    nonempty_ratio = nonempty_count / n                   # want close to 1
    heading_ratio = min(heading_count / n, 1.0)           # ≥1 heading/page ideal
    avg_line_len = total_line_len / total_lines
    # Good markdown has moderate line lengths (20-120 chars).
    # Very short (<10) → fragmented text;  very long (>300) → wall of text.
    len_score = 1.0 if 20 <= avg_line_len <= 120 else max(0, 1 - abs(avg_line_len - 70) / 200)

    return 0.35 * nonempty_ratio + 0.30 * heading_ratio + 0.35 * len_score


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

def _pick_strategy(pdf_path: Path) -> str:
    """
    Decide which extraction strategy to use based on PDF characteristics.

    Returns "fitz" or "pymupdf4llm".

    Decision signals (checked in order of cost):
      1. Metadata   – creator/producer mentions a presentation tool  → fitz
      2. Geometry    – landscape + uniform page sizes                 → fitz
      3. Image ratio – >40% image blocks in a sample of pages        → fitz
      4. Otherwise   – default to pymupdf4llm (best for native docs)
    """
    doc = fitz.open(pdf_path)

    # Signal 1: creator metadata
    if _is_presentation_origin(doc):
        doc.close()
        return "fitz"

    # Signal 2: landscape slides with identical dimensions
    if _is_landscape(doc) and _has_uniform_page_size(doc):
        doc.close()
        return "fitz"

    # Signal 3: high image content
    if _image_block_ratio(doc) > 0.4:
        doc.close()
        return "fitz"

    doc.close()
    return "pymupdf4llm"


def extract_text_from_pdf(pdf_path: Path) -> List[Tuple[str, str]]:
    """
    Extracts text from a PDF.

    Uses structural heuristics (metadata, geometry, image ratio) to pick the
    best strategy upfront.  When pymupdf4llm is chosen, a quality check on
    the output can still trigger a fallback to font-aware fitz extraction.
    """
    strategy = _pick_strategy(pdf_path)

    if strategy == "fitz":
        return _extract_via_fitz(pdf_path)

    # Try pymupdf4llm and verify output quality
    pages_md = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)

    # Quick sparseness check
    total_chars = sum(len(p.get("text", "")) for p in pages_md)
    avg_chars = total_chars / max(len(pages_md), 1)
    if avg_chars < _MIN_CHARS_PER_PAGE:
        return _extract_via_fitz(pdf_path)

    # Structural quality check
    quality = _score_md_quality(pages_md)
    if quality < 0.35:
        return _extract_via_fitz(pdf_path)

    # Good quality – parse into (title, body) tuples
    slides = []
    for i, page in enumerate(pages_md):
        md = page.get("text", "").strip()
        if not md:
            slides.append((f"Slide {i + 1}", ""))
            continue
        lines = md.split("\n", 1)
        title = lines[0].lstrip("#").strip() or f"Slide {i + 1}"
        body = lines[1].strip() if len(lines) > 1 else ""
        slides.append((title, body))
    return slides


def write_slides_md(slides: List[Tuple[str, str]], out_path: Path):
    """Writes extracted slides to markdown format."""
    with open(out_path, "w", encoding="utf-8") as f:
        for title, body in slides:
            f.write(f"# {title}\n\n")
            f.write(f"{body}\n\n")
            f.write("---\n\n")
