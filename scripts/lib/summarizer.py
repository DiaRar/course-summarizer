import time
from pathlib import Path
from scripts.config import settings
from scripts.lib.llm import call_text

SYSTEM_PROMPT = """You are an expert academic synthesizer.
You summarize lecture slides into exam-grade LaTeX notes.
- Use clean, academic LaTeX.
- Include all key definitions, formulas, and proofs.
- Reference extracted images using \\includegraphics.
- Structure with \\section and \\subsection.
- IMPORTANT: Do NOT include the full slide screenshot (`slide_png`) unless it is a complex diagram or chart that cannot be described by text. If the slide is mostly text, rely on the extracted text and do NOT include the image.
- Prioritize using `extracted_images` over `slide_png` if available.
"""

MAX_RETRIES = 3

def summarize_lecture(
    lecture_dir: Path,
    slide_blocks_file: Path,
    system_prompt_override: str = None
) -> None:
    """Summarizes a whole lecture into lecture_notes.tex."""
    
    if not slide_blocks_file.exists():
        raise RuntimeError(f"Missing slides.json at {slide_blocks_file}")
        
    slides_content = slide_blocks_file.read_text(encoding="utf-8")
    
    prompt = f"""
    Here is the content of a lecture (JSON format with slide text and image paths).
    Summarize this into a single cohesive LaTeX document (only body, no preamble).
    
    Content:
    {slides_content}
    """
    
    sys_prompt = system_prompt_override or SYSTEM_PROMPT
    
    print(f"[info] Summarizing lecture {lecture_dir.name}...")
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            out = call_text(
                model=settings.text_model,
                system_prompt=sys_prompt,
                user_prompt=prompt,
                temperature=0.1,
                max_output_tokens=settings.rewrite_max_output_tokens * 10
            )
            
            if "```latex" in out:
                out = out.split("```latex")[1].split("```")[0].strip()
            elif "```" in out:
                out = out.split("```")[1].split("```")[0].strip()
                
            (lecture_dir / "lecture_notes.tex").write_text(out, encoding="utf-8")
            print(f"[ok] Wrote lecture_notes.tex")
            return
            
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"[warn] Summarization attempt {attempt}/{MAX_RETRIES} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"[error] Summarization failed after {MAX_RETRIES} attempts: {e}")
