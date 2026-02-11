import re
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple

from scripts.config import settings
from scripts.lib.llm import call_text, call_vision

@dataclass
class SlideBlock:
    slide_index: int
    title: str
    body_md: str
    slide_png: str
    extracted_images: List[str]

SLIDE_HEADER_RE = re.compile(r"^(#{1,3})\s+(.*)\s*$")

def parse_slides_md(md_text: str) -> List[tuple[str, str]]:
    """Splits markdown into (title, body) tuples based on headers."""
    lines = md_text.splitlines()
    heading_idxs = []
    for i, line in enumerate(lines):
        m = SLIDE_HEADER_RE.match(line)
        if m:
            level = len(m.group(1))
            heading_idxs.append((i, level, m.group(2).strip()))

    if not heading_idxs:
        return [("Lecture", md_text.strip())]

    levels = [lvl for _, lvl, _ in heading_idxs]
    # Prefer level 2, else 1
    split_level = 2 if 2 in levels else 1
    splits = [(i, title) for i, lvl, title in heading_idxs if lvl == split_level]
    
    if not splits:
        split_level = min(levels)
        splits = [(i, title) for i, lvl, title in heading_idxs if lvl == split_level]

    sections = []
    for j, (start_idx, title) in enumerate(splits):
        end_idx = splits[j + 1][0] if j + 1 < len(splits) else len(lines)
        body = "\n".join(lines[start_idx + 1 : end_idx]).strip()
        sections.append((title, body))
    return sections

def find_extracted_images(body_md: str) -> List[str]:
    imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body_md)
    out = []
    for p in imgs:
        p = p.strip()
        # Clean paths like ./img/ -> img/
        clean_p = p.replace("./", "")
        if clean_p.startswith("img/"):
            out.append(clean_p)
    return out

from tqdm import tqdm

def clean_body_md(title: str, body: str) -> str:
    # Text-only quick fix
    prompt = (
        "Fix obvious OCR/transcription glitches. Keep format/math. No summarizing.\n"
        "IMPORTANT: Output ONLY the corrected text. Do NOT say 'Okay I will fix' or provide any preamble.\n"
        f"Title: {title}\nBody:\n{body}"
    )
    try:
        return call_text(
            model=settings.mini_text_model,
            system_prompt="Fix typos/spacing/OCR junk only. Output ONLY the fixed text.",
            user_prompt=prompt,
            temperature=0.0,
            max_output_tokens=2000
        ).strip()
    except Exception:
        return body

def batch_clean_bodies_vision(
    lecture_dir: Path,
    titles: List[str],
    bodies: List[str],
    slide_png_rels: List[str]
) -> List[str]:
    """
    Refines slide text using the vision model and slide PNGs.
    Batches requests to save calls.
    """
    if not settings.glitch_fix_with_png:
        return bodies

    final_cleaned = list(bodies)
    batch_size = settings.glitch_fix_batch_size
    
    # Process in chunks with TQDM
    total_batches = (len(bodies) + batch_size - 1) // batch_size
    
    for start in tqdm(range(0, len(bodies), batch_size), desc="Vision Cleanup", total=total_batches, unit="batch"):
        end = min(len(bodies), start + batch_size)
        
        batch_indices = range(start, end) # Global indices
        
        valid_batch_items = [] # (global_idx, title, body, img_path)
        
        for g_idx in batch_indices:
            t = titles[g_idx]
            b = bodies[g_idx]
            rel = slide_png_rels[g_idx]
            img_abs = lecture_dir / rel
            if img_abs.exists():
                valid_batch_items.append((g_idx, t, b, str(img_abs)))
        
        if not valid_batch_items:
            continue
            
        # Call LLM
        img_paths = [x[3] for x in valid_batch_items]
        
        prompt_lines = [
            "Correct the markdown text for these slides using the images.",
            "Strictly follow the order. Use delimiters '=== SLIDE N ===' where N is the slide number provided below.",
            "IMPORTANT: Output ONLY the requested format. No conversational filler.",
            ""
        ]
        
        for i, (g_idx, t, b, _) in enumerate(valid_batch_items, start=1):
            prompt_lines.extend([
                f"=== SLIDE {i} INPUT ===",
                f"Title: {t}",
                f"Markdown:\n{b}",
                ""
            ])
            
        try:
            out = call_vision(
                model=settings.vision_model,
                system_prompt="Refine slide text from images. Keep format. Output ONLY the content for each slide.",
                user_text="\n".join(prompt_lines),
                image_paths=img_paths,
                max_output_tokens=min(8192, 1000 * len(valid_batch_items))
            )

            # Parse
            chunks = re.split(r"=== SLIDE (\d+) ===", out)
            for k in range(1, len(chunks), 2):
                num_str = chunks[k]
                content = chunks[k+1].strip()
                if num_str.isdigit():
                    local_idx = int(num_str) # 1-based index in this batch
                    
                    if 1 <= local_idx <= len(valid_batch_items):
                        # Map to global
                        global_idx = valid_batch_items[local_idx-1][0]
                        final_cleaned[global_idx] = content
                        
        except Exception as e:
             print(f"[warn] batch processing error: {e}")

    return final_cleaned

def rewrite_body_md(title: str, body: str) -> str:
    """Rewrite to fix broken math/placeholders."""
    if not settings.rewrite_max_output_tokens:
        return body
        
    prompt = (
        "Fix corrupted formulas/placeholders. Keep structure/tables/bullets.\n"
        "IMPORTANT: Output ONLY the corrected markdown. Do NOT chat.\n"
        f"Title: {title}\nMarkdown:\n{body}"
    )
    try:
        return call_text(
            model=settings.text_model,
            system_prompt="Technical editor fixing formulas. Output ONLY the fixed content.",
            user_prompt=prompt,
            temperature=0.0,
            max_output_tokens=settings.rewrite_max_output_tokens
        ).strip()
    except Exception:
        return body
