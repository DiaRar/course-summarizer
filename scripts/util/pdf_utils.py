
import fitz  # pymupdf
from pathlib import Path
from typing import List, Tuple
import re

def extract_text_from_pdf(pdf_path: Path) -> List[Tuple[str, str]]:
    """
    Extracts text from a PDF, returning a list of (title, body) tuples
    simulating slides.
    
    Since PDFs don't have explicit "slides", we treat each page as a slide.
    We attempt to heuristically detect a title from the first line(s) of the page.
    """
    doc = fitz.open(pdf_path)
    slides = []
    
    for i, page in enumerate(doc):
        text = page.get_text("text")
        lines = text.splitlines()
        
        # Heuristic: First non-empty line is the title
        title = f"Slide {i+1}"
        body_lines = []
        
        found_title = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if not found_title:
                title = line
                found_title = True
            else:
                body_lines.append(line)
        
        body = "\n".join(body_lines)
        slides.append((title, body))
        
    return slides

def write_slides_md(slides: List[Tuple[str, str]], out_path: Path):
    """
    Writes the extracted slides to a markdown file in the format expected by build_lecture_input.py.
    Format:
    
    # Title
    Body content...
    
    ---
    """
    with open(out_path, "w", encoding="utf-8") as f:
        for title, body in slides:
            f.write(f"# {title}\n\n")
            f.write(f"{body}\n\n")
            f.write("---\n\n")
