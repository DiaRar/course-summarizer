import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from scripts.config import settings
from scripts.lib.pdf_tools import pptx_to_pdf, pdf_to_pngs, latex_to_pdf
from scripts.lib.content_parser import parse_slides_md, find_extracted_images, clean_body_md, rewrite_body_md, batch_clean_bodies_vision, SlideBlock
from scripts.lib.summarizer import summarize_lecture
from scripts.lib.synthesis import synthesize_course, infer_structure
from scripts.util import pdf_utils
import json
from dataclasses import asdict
from tqdm import tqdm

def process_single_lecture(input_file: Path):
    """
    Full pipeline for one lecture file (PPTX or PDF).
    """
    print(f"[start] {input_file.name}")
    
    try:
        lecture_name = input_file.stem
        out_dir = settings.out_root / lecture_name
        out_dir.mkdir(parents=True, exist_ok=True)
        
        slides_md_path = out_dir / "slides.md"
        slides_png_dir = out_dir / "slides_png"
        
        # 1. Conversion / Extraction
        if input_file.suffix.lower() == ".pptx":
            # PPTX -> PDF (temp) -> PNGs
            tmp_pdf = out_dir / "_temp.pdf"
            pptx_to_pdf(input_file, tmp_pdf)
            pdf_to_pngs(tmp_pdf, slides_png_dir, dpi=settings.dpi)
            
            # PPTX -> Markdown
            # using pptx2md-diar via subprocess as it's a CLI tool mostly
            # We can import if available, but CLI is safer given the deps
            import subprocess
            cmd = ["pptx2md", str(input_file), "-o", str(out_dir / "slides.md"), "--disable-image"] 
            # Check if pptx2md is installed or use the one in scripts?
            # Original code used `scripts/convert_with_pptx2md.py` which wraps `pptx2md`.
            # We should assume `pptx2md` is in path or venv.
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
            
            # Clean temp PDF
            if tmp_pdf.exists():
                tmp_pdf.unlink()
                
        elif input_file.suffix.lower() == ".pdf":
            # PDF -> PNGs
            pdf_to_pngs(input_file, slides_png_dir, dpi=settings.dpi)
            
            # PDF -> Text (Markdown)
            slides_text = pdf_utils.extract_text_from_pdf(input_file)
            pdf_utils.write_slides_md(slides_text, slides_md_path)
            
        else:
            print(f"[skip] Unknown format: {input_file}")
            return

        # 2. Content Parse & Cleanup
        md_content = slides_md_path.read_text(encoding="utf-8")
        sections = parse_slides_md(md_content)
        
        titles = [t for t, _ in sections]
        bodies = [b for _, b in sections]
        slide_png_rels = [f"slides_png/slide{i+1:02d}.png" for i in range(len(sections))]
        
        # Vision Batch Fix (if enabled)
        if settings.glitch_fix_with_png:
            bodies = batch_clean_bodies_vision(out_dir, titles, bodies, slide_png_rels)
            
        blocks = []
        for i, (title, body, png_rel) in enumerate(tqdm(zip(titles, bodies, slide_png_rels), total=len(titles), desc="Text Cleanup")):
            # Text Only Fix / Rewrite
            body = clean_body_md(title, body)
            body = rewrite_body_md(title, body)
            
            extracted = find_extracted_images(body)
            blocks.append(SlideBlock(
                slide_index=i,
                title=title,
                body_md=body,
                slide_png=png_rel,
                extracted_images=extracted
            ))
            
        # Write slides.json
        slides_json_path = out_dir / "slides.json"
        with open(slides_json_path, "w") as f:
            json.dump([asdict(b) for b in blocks], f, indent=2, ensure_ascii=False)
            
        # Overwrite slides.md with the CLEANED content so user sees the fix
        with open(slides_md_path, "w", encoding="utf-8") as f:
            for b in blocks:
                f.write(f"# {b.title}\n\n")
                f.write(f"{b.body_md}\n\n")
                f.write("---\n\n")
            
        # 3. Summarize
        summarize_lecture(out_dir, slides_json_path)
        
        print(f"[done] {input_file.name}")
        
    except Exception as e:
        print(f"[error] Failed {input_file.name}: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="Course Summarizer CLI")
    parser.add_argument("command", choices=["process", "synthesize", "clean"], default="process", nargs="?")
    parser.add_argument("--lectures_dir", default=None)
    parser.add_argument("--out_root", default=None)
    parser.add_argument("--compile-pdf", action="store_true", help="Compile LaTeX to PDF after synthesis")
    parser.add_argument("--clean-intermediate", action="store_true", help="Remove intermediate files like PNGs")

    parser.add_argument("--limit", type=int, default=None, help="Limit number of lectures to process")
    
    args = parser.parse_args()
    
    # Update settings from args
    if args.lectures_dir:
        settings.lectures_dir = Path(args.lectures_dir)
    if args.out_root:
        settings.out_root = Path(args.out_root)
        
    cmd = args.command
    
    if cmd == "process":
        settings.out_root.mkdir(parents=True, exist_ok=True)
        
        inputs = list(settings.lectures_dir.glob("*.pptx")) + list(settings.lectures_dir.glob("*.pdf"))
        # Filter hidden
        inputs = [p for p in inputs if not p.name.startswith(".")]
        inputs.sort()
        
        if args.limit:
            inputs = inputs[:args.limit]
            
        print(f"Found {len(inputs)} lectures (limit={args.limit}).")
        
        from concurrent.futures import as_completed

        with ThreadPoolExecutor(max_workers=settings.max_workers) as ex:
             futures = [ex.submit(process_single_lecture, p) for p in inputs]
             for _ in tqdm(as_completed(futures), total=len(inputs), desc="Processing Lectures"):
                 pass
             
        # After processing, usually synthesis follows automatically?
        # Let's run synthesis automatically if process was run
        print("\n[info] Processing complete. Running synthesis...")
        synthesize_course(settings.out_root)
        
        if args.compile_pdf:
            tex_file = settings.out_root / "synthesized" / "course_notes.tex"
            if tex_file.exists():
                try:
                    pdf = latex_to_pdf(tex_file, clean=True)
                    print(f"[success] Generated PDF: {pdf}")
                except Exception as e:
                    print(f"[error] PDF compilation failed: {e}")
                    
        if args.clean_intermediate:
            # Implement cleanup
            # rm slides_png folders?
            print("[info] Cleaning intermediate files...")
            for d in settings.out_root.iterdir():
                if d.is_dir() and (d / "slides_png").exists():
                    import shutil
                    shutil.rmtree(d / "slides_png")
            print("[ok] Cleanup done.")

    elif cmd == "synthesize":
        synthesize_course(settings.out_root)
        if args.compile_pdf:
            tex_file = settings.out_root / "synthesized" / "course_notes.tex"
            if tex_file.exists():
                latex_to_pdf(tex_file, clean=True)

    elif cmd == "clean":
        if settings.out_root.exists():
            import shutil
            shutil.rmtree(settings.out_root)
            print("Output directory cleaned.")

if __name__ == "__main__":
    main()
