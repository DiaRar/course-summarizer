from __future__ import annotations

import argparse
from pathlib import Path

from pptx2md import convert, ConversionConfig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pptx", required=True)
    ap.add_argument("--out_dir", required=True, help="e.g. out/Lecture1_W1_Fall2025")
    ap.add_argument("--disable_notes", action="store_true", default=False)
    args = ap.parse_args()

    pptx_path = Path(args.pptx)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "slides.md"
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    cfg = ConversionConfig(
        pptx_path=pptx_path,
        output_path=md_path,
        image_dir=img_dir,
        disable_notes=args.disable_notes,
    )
    try:
        convert(cfg)
    except Exception as e:
        # Some decks have missing notes slides or malformed shapes; retry without notes + guard shapes
        print(f"[warn] pptx2md failed ({e}); retrying with notes disabled and text-guard")
        cfg.disable_notes = True
        import pptx2md.parser as parser  # type: ignore

        orig_process_title = parser.process_title
        orig_process_shapes = parser.process_shapes

        def safe_process_title(config, shape, slide_id):
            if not getattr(shape, "has_text_frame", False):
                return None
            return orig_process_title(config, shape, slide_id)

        def safe_process_shapes(config, shapes, slide_id):
            items = orig_process_shapes(config, shapes, slide_id)
            return [x for x in items if x is not None]

        parser.process_title = safe_process_title  # type: ignore
        parser.process_shapes = safe_process_shapes  # type: ignore
        try:
            convert(cfg)
        finally:
            parser.process_title = orig_process_title  # restore
            parser.process_shapes = orig_process_shapes  # restore

    print(f"[ok] pptx2md -> {md_path} (images in {img_dir})")


if __name__ == "__main__":
    main()
