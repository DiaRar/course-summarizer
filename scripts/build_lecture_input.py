from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

from _openai import ModelConfig, responses_text, responses_vision


@dataclass
class SlideBlock:
    slide_index: int
    title: str
    body_md: str
    slide_png: str  # slides_png/slideNN.png
    extracted_images: List[str]  # img/...


SLIDE_HEADER_RE = re.compile(r"^(#{1,3})\s+(.*)\s*$")


def parse_slides_md(md_text: str) -> List[tuple[str, str]]:
    """
    Returns a list of (title, body_md) sections.
    Heuristic: split on headings starting with ## (or # if no ## exists).
    """
    lines = md_text.splitlines()
    # Find headings
    heading_idxs = []
    for i, line in enumerate(lines):
        m = SLIDE_HEADER_RE.match(line)
        if m:
            level = len(m.group(1))
            # Prefer splitting on level 2 headings if present, else level 1
            heading_idxs.append((i, level, m.group(2).strip()))

    if not heading_idxs:
        return [("Lecture", md_text.strip())]

    # choose split level
    levels = [lvl for _, lvl, _ in heading_idxs]
    split_level = 2 if 2 in levels else 1

    splits = [(i, title) for i, lvl, title in heading_idxs if lvl == split_level]
    if not splits:
        # fallback to first heading level
        split_level = min(levels)
        splits = [(i, title) for i, lvl, title in heading_idxs if lvl == split_level]

    sections: List[tuple[str, str]] = []
    for j, (start_idx, title) in enumerate(splits):
        end_idx = splits[j + 1][0] if j + 1 < len(splits) else len(lines)
        body = "\n".join(lines[start_idx + 1 : end_idx]).strip()
        sections.append((title, body))
    return sections


def find_extracted_images_in_body(body_md: str) -> List[str]:
    # Markdown image syntax: ![](path) or ![alt](path)
    imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body_md)
    # keep only paths under img/
    out = []
    for p in imgs:
        p = p.strip()
        if p.startswith("img/") or p.startswith("./img/"):
            out.append(p.replace("./", ""))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lecture_dir", required=True, help="e.g. out/Lecture1_W1_Fall2025")
    ap.add_argument(
        "--glitch_fix_model",
        default=ModelConfig().mini_text_model,
        help="small text model (e.g., gpt-5-mini) to auto-fix obvious OCR/spacing glitches in slide bodies; set to '' to disable",
    )
    ap.add_argument(
        "--glitch_fix_with_png",
        action="store_true",
        help="use slide PNG plus markdown to recover missing words (vision model); slower/costlier, only use for problem decks",
    )
    ap.add_argument(
        "--glitch_fix_vision_model",
        default=ModelConfig().vision_model,
        help="vision model to use when --glitch_fix_with_png is enabled",
    )
    ap.add_argument(
        "--glitch_fix_batch_size",
        type=int,
        default=5,
        help="number of slide PNGs to process per vision request (only when glitch_fix_with_png is enabled)",
    )
    ap.add_argument(
        "--rewrite_with_model",
        default=None,
        help="optional larger text model (e.g., gpt-5.2) to repair equations/blank placeholders per slide after cleaning; set to '' to disable",
    )
    ap.add_argument(
        "--rewrite_max_output_tokens",
        type=int,
        default=1200,
        help="token cap for rewrite model output",
    )
    args = ap.parse_args()

    lecture_dir = Path(args.lecture_dir)
    md_path = lecture_dir / "slides.md"
    if not md_path.exists():
        raise RuntimeError(f"Missing {md_path}. Run convert_with_pptx2md.py first.")

    md_text = md_path.read_text(encoding="utf-8")
    sections = parse_slides_md(md_text)

    # Optional lightweight cleanup pass using a small text model to patch obvious glitches
    def clean_body_md(title: str, body: str) -> str:
        if not args.glitch_fix_model:
            return body
        prompt = (
            "Fix obvious OCR or transcription glitches in this slide body without changing meaning.\n"
            "- Keep Markdown structure and any LaTeX/math as-is unless clearly broken.\n"
            "- Do not summarize or shorten.\n"
            "- Only fix typos/spacing/odd control characters.\n\n"
            f"Title: {title}\n\nBody:\n{body}"
        )
        try:
            out = responses_text(
                model=args.glitch_fix_model,
                system="You are a minimal proofreader. Only fix clear typos/spacing/OCR junk; do not rewrite content.",
                user=prompt,
                temperature=0.0,
                max_output_tokens=min(2000, max(300, len(body) // 2)),
            )
            return out.strip() or body
        except Exception:
            return body

    # Optional vision-assisted recovery in batches (default batch size = 5 PNGs per call)
    def batch_clean_bodies_with_png(titles: List[str], bodies: List[str], slide_png_rels: List[str]) -> List[str]:
        if not args.glitch_fix_with_png:
            return bodies

        cleaned = list(bodies)
        batch_size = max(1, args.glitch_fix_batch_size)
        for start in range(0, len(bodies), batch_size):
            end = min(len(bodies), start + batch_size)
            batch_titles = titles[start:end]
            batch_bodies = bodies[start:end]
            batch_pngs = slide_png_rels[start:end]

            image_paths = []
            entries = []
            for idx, (t, b, rel) in enumerate(zip(batch_titles, batch_bodies, batch_pngs), start=1):
                img_abs = lecture_dir / rel
                if not img_abs.exists():
                    entries.append((idx, t, b, None))
                    continue
                image_paths.append(str(img_abs))
                entries.append((idx, t, b, str(img_abs)))

            if not image_paths:
                continue

            # Build a single prompt with clear delimiters for each slide
            prompt_lines = [
                "Using the slide images and current markdown, fix missing or corrupted text for each slide.",
                "- Preserve Markdown structure and math/LaTeX where present.",
                "- Do not summarize; keep all bullet points.",
                "- Only correct transcription/spacing/typos and fill blanks that are visible on the image.",
                "- Respond exactly with one block per slide, delimited as:",
                "=== SLIDE 1 ===",
                "<fixed markdown>",
                "=== SLIDE 2 ===",
                "<fixed markdown>",
                "",
            ]
            for idx, t, b, _ in entries:
                prompt_lines.append(f"=== SLIDE {idx} INPUT ===")
                prompt_lines.append(f"Title: {t}")
                prompt_lines.append("Current Markdown:")
                prompt_lines.append(b)
                prompt_lines.append("")

            prompt = "\n".join(prompt_lines)

            try:
                max_tokens = min(6000, max(800, sum(len(b) for b in batch_bodies) // 2))
                out = responses_vision(
                    model=args.glitch_fix_vision_model,
                    system="You repair slide text using the provided images. Keep formatting, bullets, and formulas; only patch missing/garbled text.",
                    user_text=prompt,
                    image_paths=image_paths,
                    max_output_tokens=max_tokens,
                )
                # Parse the response by delimiters
                parts = out.split("=== SLIDE")
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    # Expect format "N ===\n<content>" or "N ===\r\n"
                    if part[0].isdigit():
                        num_str, _, content = part.partition("===")
                        try:
                            num = int(num_str.strip())
                        except Exception:
                            continue
                        content = content.strip()
                        # Map back to global index
                        global_idx = start + (num - 1)
                        if 0 <= global_idx < len(cleaned) and content:
                            cleaned[global_idx] = content
            except Exception:
                # If batch fails, leave originals
                continue

        return cleaned

    def rewrite_body_md(title: str, body: str) -> str:
        model = (args.rewrite_with_model or "").strip()
        if not model:
            return body
        prompt = (
            "Rewrite this slide markdown to fix corrupted formulas, missing math symbols, and placeholder blanks like 'times' or empty underscores.\n"
            "- Preserve headings and bullet structure.\n"
            "- Keep tables; fill missing numeric placeholders with descriptive text if numbers are absent.\n"
            "- Do NOT shorten or summarize; keep as close to original meaning as possible.\n\n"
            f"Title: {title}\n\nMarkdown:\n{body}"
        )
        try:
            out = responses_text(
                model=model,
                system="You are a careful technical editor. You fix corrupted formulas and placeholders while preserving structure.",
                user=prompt,
                temperature=0.0,
                max_output_tokens=args.rewrite_max_output_tokens,
            )
            return out.strip() or body
        except Exception:
            return body

    titles = [t for t, _ in sections]
    bodies = [b for _, b in sections]
    original_bodies = list(bodies)
    slide_png_rels = [str(Path("slides_png") / f"slide{i+1:02d}.png") for i in range(len(sections))]

    bodies = batch_clean_bodies_with_png(titles, bodies, slide_png_rels)

    blocks: List[SlideBlock] = []
    for i, (title, body, orig_body, slide_png_rel) in enumerate(zip(titles, bodies, original_bodies, slide_png_rels)):
        if body != orig_body:
            print(f"[glitch_fix] slide {i+1}: updated content via vision/text cleanup")
        body = clean_body_md(title, body)
        slide_png = slide_png_rel
        extracted_images = find_extracted_images_in_body(body)
        blocks.append(
            SlideBlock(
                slide_index=i,
                title=title,
                body_md=body,
                slide_png=slide_png,
                extracted_images=extracted_images,
            )
        )

    out_json = lecture_dir / "slides.json"
    out_json.write_text(json.dumps([asdict(b) for b in blocks], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] wrote {out_json} ({len(blocks)} blocks)")


if __name__ == "__main__":
    main()
