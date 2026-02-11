
from __future__ import annotations

import argparse
from pathlib import Path
import concurrent.futures
from typing import List
import sys

from handlers import PptxHandler, PdfHandler, InputHandler

def main() -> None:
    ap = argparse.ArgumentParser(description="Process course materials (PPTX/PDF) into summarized notes.")
    ap.add_argument("--lectures_dir", default="lectures", help="Directory containing input files")
    ap.add_argument("--out_root", default="out", help="Output directory")
    ap.add_argument("--dpi", type=int, default=200, help="DPI for slide rendering")
    ap.add_argument("--caption_slide_pngs", action=argparse.BooleanOptionalAction, default=True, help="Caption full slide PNGs (Default: True)")
    ap.add_argument("--max_workers", type=int, default=2, help="Parallel workers")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of lectures to process")
    
    # Glitch fix / Rewrite args
    # Defaults enabled as per user request
    from llm_client import ModelConfig
    defaults = ModelConfig()
    
    ap.add_argument("--glitch_fix_with_png", action=argparse.BooleanOptionalAction, default=True, help="Use vision to fix slides (Default: True)")
    ap.add_argument("--glitch_fix_model", default=defaults.mini_text_model, help=f"Model for text glitch fix (Default: {defaults.mini_text_model})")
    ap.add_argument("--glitch_fix_vision_model", default=defaults.vision_model, help=f"Model for vision glitch fix (Default: {defaults.vision_model})")
    ap.add_argument("--glitch_fix_batch_size", type=int, default=5)
    
    # Rewrite with model enabled by default
    ap.add_argument("--rewrite_with_model", default=defaults.text_model, help=f"Model for slide rewriting (Default: {defaults.text_model})")
    ap.add_argument("--rewrite_max_output_tokens", type=int, default=1200)
    
    # Prompting
    ap.add_argument("--system_prompt", default=None, help="Custom system prompt for summarization")

    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    lectures_dir = Path(args.lectures_dir)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # Gather inputs
    # We look for .pptx and .pdf
    # If a lecture has both, we might duplicate or prefer one.
    # For now, let's just process everything found.
    
    inputs: List[Path] = []
    inputs.extend(sorted(lectures_dir.glob("*.pptx")))
    inputs.extend(sorted(lectures_dir.glob("*.pdf")))
    
    # Filter out hidden files
    inputs = [p for p in inputs if not p.name.startswith("._") and not p.name.startswith(".")]

    if not inputs:
        print(f"[warn] No .pptx or .pdf files found in {lectures_dir}")
        return

    if args.limit:
        inputs = inputs[:args.limit]

    print(f"[info] Found {len(inputs)} files to process.")

    def process_file(input_file: Path) -> None:
        try:
            handler: InputHandler
            if input_file.suffix.lower() == ".pptx":
                handler = PptxHandler(input_file, out_root, root)
            elif input_file.suffix.lower() == ".pdf":
                handler = PdfHandler(input_file, out_root, root)
            else:
                print(f"[skip] Unsupported file type: {input_file}")
                return
            
            print(f"[start] Processing {input_file.name}...")
            handler.process(args)
            print(f"[done] Finished {input_file.name}")
        except Exception as e:
            print(f"[error] Failed processing {input_file.name}: {e}")
            import traceback
            traceback.print_exc()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
        futures = [ex.submit(process_file, p) for p in inputs]
        for f in futures:
            f.result()

    # After processing all lectures, we supposedly run specific steps like infer_structure and synthesize_course.
    # However, those scripts assume a specific directory structure.
    # InputHandlers create specific output directories.
    # infer_structure.py scans out_root.
    
    print("[info] Running structure inference...")
    try:
        import subprocess
        subprocess.check_call([sys.executable, str(root / "infer_structure.py"), "--out_root", str(out_root)])
    except Exception as e:
        print(f"[warn] infer_structure failed: {e}")

    print("[info] Running course synthesis...")
    try:
        cmd = [sys.executable, str(root / "synthesize_course.py"), "--out_root", str(out_root)]
        # synthesize_course.py doesn't take system_prompt yet, but we might want to add valid args if we updated it
        subprocess.check_call(cmd)
    except Exception as e:
        print(f"[warn] synthesize_course failed: {e}")

    print("[ok] All done.")

if __name__ == "__main__":
    main()
