from __future__ import annotations

import argparse
import concurrent.futures
import re
import subprocess
import threading
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("[run]", " ".join(cmd))
    subprocess.check_call(cmd)


def extract_lecture_number(path: Path) -> int:
    name = path.stem  # Lecture10_W9_Fall2025
    m = re.search(r"lecture\s*(\d+)", name, flags=re.I)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    return 10**9  # send unparseable names to the end


def lecture_dir_name(path: Path) -> str:
    n = extract_lecture_number(path)
    if n != 10**9:
        return f"Lecture{n}"
    return path.stem


_render_lock = threading.Lock()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lectures_dir", default="lectures")
    ap.add_argument("--out_root", default="out")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--disable_notes", action="store_true", default=False)
    ap.add_argument("--caption_slide_pngs", action="store_true", default=False)
    ap.add_argument(
        "--max_workers",
        type=int,
        default=2,
        help="number of lectures to process in parallel (2–3 recommended)",
    )
    ap.add_argument(
        "--glitch_fix_with_png",
        action="store_true",
        help="build_lecture_input: use slide PNG plus markdown to recover missing text",
    )
    ap.add_argument(
        "--glitch_fix_model",
        default=None,
        help="build_lecture_input: text model for glitch fixing; set '' to disable (defaults to gpt-5-mini if omitted)",
    )
    ap.add_argument(
        "--glitch_fix_vision_model",
        default=None,
        help="build_lecture_input: vision model when glitch_fix_with_png is enabled",
    )
    ap.add_argument(
        "--glitch_fix_batch_size",
        type=int,
        default=None,
        help="build_lecture_input: batch size for slide PNG vision fixing (default 5 if not provided)",
    )
    ap.add_argument(
        "--rewrite_with_model",
        default=None,
        help="build_lecture_input: larger text model to repair formulas/placeholders per slide (e.g., gpt-5.2); set '' to disable",
    )
    ap.add_argument(
        "--rewrite_max_output_tokens",
        type=int,
        default=None,
        help="build_lecture_input: max output tokens for rewrite model (defaults to script default if None)",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    lectures_dir = Path(args.lectures_dir)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    pptxs = sorted(lectures_dir.glob("*.pptx"), key=lambda p: (extract_lecture_number(p), p.name))
    if not pptxs:
        raise RuntimeError(f"No pptx files found in {lectures_dir}")

    def process_pptx(pptx: Path) -> None:
        lec_dir = lecture_dir_name(pptx)
        out_dir = out_root / lec_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        # A) pptx2md conversion
        cmd = ["python", str(root / "convert_with_pptx2md.py"), "--pptx", str(pptx), "--out_dir", str(out_dir)]
        if args.disable_notes:
            cmd.append("--disable_notes")
        run(cmd)

        # B) render slide PNGs (fidelity fallback); LibreOffice can be unhappy concurrently, so lock
        with _render_lock:
            run(["python", str(root / "render_slides.py"), "--pptx", str(pptx), "--out_dir", str(out_dir), "--dpi", str(args.dpi)])

        # C) build slides.json
        bli_cmd = ["python", str(root / "build_lecture_input.py"), "--lecture_dir", str(out_dir)]
        if args.glitch_fix_with_png:
            bli_cmd.append("--glitch_fix_with_png")
        if args.glitch_fix_model is not None:
            bli_cmd.extend(["--glitch_fix_model", args.glitch_fix_model])
        if args.glitch_fix_vision_model is not None:
            bli_cmd.extend(["--glitch_fix_vision_model", args.glitch_fix_vision_model])
        if args.glitch_fix_batch_size is not None:
            bli_cmd.extend(["--glitch_fix_batch_size", str(args.glitch_fix_batch_size)])
        if args.rewrite_with_model is not None:
            bli_cmd.extend(["--rewrite_with_model", args.rewrite_with_model])
        if args.rewrite_max_output_tokens is not None:
            bli_cmd.extend(["--rewrite_max_output_tokens", str(args.rewrite_max_output_tokens)])
        run(bli_cmd)

        # D) caption images (pptx2md exported + optional slide PNGs)
        cmd = ["python", str(root / "caption_images.py"), "--lecture_dir", str(out_dir)]
        if args.caption_slide_pngs:
            cmd.append("--caption_slide_pngs")
        run(cmd)

        # E) summarize lecture (MD + LaTeX)
        run(["python", str(root / "summarize_lecture.py"), "--lecture_dir", str(out_dir)])

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
        futures = [ex.submit(process_pptx, pptx) for pptx in pptxs]
        for f in futures:
            f.result()

    # F) infer chapter/part structure
    run(["python", str(root / "infer_structure.py"), "--out_root", str(out_root)])

    # G) synthesize course notes
    run(["python", str(root / "synthesize_course.py"), "--out_root", str(out_root)])

    print("[ok] all done")


if __name__ == "__main__":
    main()
