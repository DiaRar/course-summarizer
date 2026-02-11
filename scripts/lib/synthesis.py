import json
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any

from scripts.config import settings
from scripts.lib.llm import call_text

SYSTEM_PROMPT = """You synthesize full academic course notes in LaTeX.
Strict notation consistency. Keep math correct.
Include Global Glossary.
Avoid duplication.
"""

PROMPT_TEMPLATE = """Synthesize these lecture notes into a coherent course.
Structure:
{structure_json}

Content:
{notes}

Output EXACTLY:
=== LATEX ===
<latex body>
"""

def infer_structure(out_root: Path) -> None:
    """
    Scans out_root for Lecture directories and infers a course structure (Chapters/Parts).
    Writes to out/synthesized/structure.json
    """
    # 1. Gather all lecture_notes.tex or slides.json to see what we have
    lectures = []
    for d in sorted(out_root.iterdir()):
        if d.is_dir() and (d / "lecture_notes.tex").exists():
            lectures.append(d.name)
    
    if not lectures:
        print("[warn] No processed lectures found to infer structure from.")
        return

    # Ask LLM to optimize structure
    
    prompt = f"""
    Organize these lecture folders into a logical course structure (Chapters -> Parts -> Files).
    Folders: {json.dumps(lectures)}
    
    Return JSON:
    {{
      "chapters": [
        {{
          "title": "Chapter Title",
          "parts": [
            {{ "title": "Part Title", "files": ["Lecture1_Folder"] }}
          ]
        }}
      ]
    }}
    """
    
    try:
        out = call_text(
            model=settings.mini_text_model,
            system_prompt="Organize course structure.",
            user_prompt=prompt,
            temperature=0.0,
            max_output_tokens=2000
        )
        # simplistic json extraction
        if "```json" in out:
            out = out.split("```json")[1].split("```")[0].strip()
        elif "```" in out:
            out = out.split("```")[1].split("```")[0].strip()
            
        structure = json.loads(out)
        
        synth_dir = out_root / "synthesized"
        synth_dir.mkdir(parents=True, exist_ok=True)
        (synth_dir / "structure.json").write_text(json.dumps(structure, indent=2), encoding="utf-8")
        print(f"[ok] Structure inferred: {len(structure.get('chapters', []))} chapters.")
        
    except Exception as e:
        print(f"[error] Structure inference failed: {e}")
        # Fallback: linear
        structure = {"chapters": [{"title": "Course Modules", "parts": [{"title": "All Lectures", "files": lectures}]}]}
        (out_root / "synthesized" / "structure.json").write_text(json.dumps(structure, indent=2), encoding="utf-8")


def synthesize_course(out_root: Path) -> None:
    synth_dir = out_root / "synthesized"
    struct_path = synth_dir / "structure.json"
    
    if not struct_path.exists():
        infer_structure(out_root)
    
    if not struct_path.exists():
        print("[error] No lecture_notes.tex found — nothing to synthesize.")
        return
        
    structure = json.loads(struct_path.read_text(encoding="utf-8"))
    
    # Gather Content
    ordered_files = []
    for ch in structure.get("chapters", []):
        for part in ch.get("parts", []):
            ordered_files.extend(part.get("files", []))
            
    # Read and rewrite paths
    chunks = []
    for lec_name in ordered_files:
        p = out_root / lec_name / "lecture_notes.tex"
        if p.exists():
            content = p.read_text(encoding="utf-8")
            # Rewrite image paths to be relative to the synthesized directory
            
            def repl(m):
                # match {img/...}
                # group(1) = img/ or slides_png/
                # group(2) = rest
                path_prefix = m.group(1)
                rest = m.group(2)
                return f"{{../{lec_name}/{path_prefix}{rest}"
            
            content = re.sub(r"\{(img/)([^}]+)", repl, content)
            content = re.sub(r"\{(slides_png/)([^}]+)", repl, content)
            
            chunks.append(f"% SOURCE: {lec_name}\n{content}")
            
    full_notes = "\n\n".join(chunks)
    
    # Call LLM
    print("[info] Synthesizing final course notes...")
    valid_json = json.dumps(structure)
    
    # Truncate if massive
    prompt = PROMPT_TEMPLATE.format(
        structure_json=valid_json,
        notes=full_notes[:400000] # Cap chars
    )
    
    try:
        out = call_text(
            model=settings.text_model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.1,
            max_output_tokens=settings.synthesis_max_output_tokens
        )
        
        if "=== LATEX ===" in out:
            out = out.split("=== LATEX ===")[1].strip()
        if "```latex" in out: # cleanup
            out = out.split("```latex")[1].split("```")[0].strip()
            
        (synth_dir / "course_notes.tex").write_text(out, encoding="utf-8")
        print(f"[ok] Wrote {synth_dir / 'course_notes.tex'}")
        
    except Exception as e:
        print(f"[error] Synthesis failed: {e}")
