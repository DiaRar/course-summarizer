from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

from llm_client import ModelConfig, call_text


SYSTEM = """You are an expert TA for a math-heavy Financial Management course.
You produce rigorous, exam-useful LaTeX notes with correct finance notation and careful timing.
You standardize notation (PV/FV, NPV, IRR, CAPM, beta, WACC, DCF, duration/convexity).
You include common exam traps (signs, t=0 vs t=1, APR vs EAR, nominal vs real)."""

PROMPT = """You are given one lecture's slide content as structured blocks.

You MUST produce LaTeX notes that INCLUDE figures/tables:
- Use \\includegraphics for images (paths under img/ or slides_png/)
- Keep tables as LaTeX tabular if feasible; otherwise present them clearly (no Markdown tables).

Write dense, technical notes. Do NOT oversimplify.

Structure:
- Executive summary (5–12 bullets)
- Definitions & notation (glossary)
- Core theory + formulas
- Procedures (step-by-step)
- Canonical examples (symbolic)
- Pitfalls / exam traps
- Quick checklist

Output format EXACTLY:

=== LATEX ===
<latex>

Input slides.json:
{slides_json}

Image captions (captions.json):
{captions_json}
"""


def split_output(text: str) -> Tuple[str, str]:
    tx_tag = "=== LATEX ==="
    if tx_tag not in text:
        return "", text.strip()
    tx = text.split(tx_tag, 1)[1].strip()
    return "", tx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lecture_dir", required=True)
    ap.add_argument("--text_model", default=ModelConfig().text_model)
    ap.add_argument("--max_output_tokens", type=int, default=6500)
    ap.add_argument("--system_prompt", default=None, help="Path to system prompt txt file, or raw string. Defaults to finance prompt if not set.")
    args = ap.parse_args()

    lecture_dir = Path(args.lecture_dir)
    slides_path = lecture_dir / "slides.json"
    if not slides_path.exists():
        raise RuntimeError("Missing slides.json. Run build_lecture_input.py first.")
    slides = json.loads(slides_path.read_text(encoding="utf-8"))

    captions_path = lecture_dir / "captions.json"
    captions: Dict[str, str] = {}
    if captions_path.exists():
        captions = json.loads(captions_path.read_text(encoding="utf-8"))

    # Slight enrichment: mark whether slide has extracted visuals
    for s in slides:
        imgs = s.get("extracted_images", []) or []
        s["has_extracted_images"] = len(imgs) > 0

    user = PROMPT.format(
        slides_json=json.dumps(slides, ensure_ascii=False, indent=2)[:180000],
        captions_json=json.dumps(captions, ensure_ascii=False, indent=2)[:60000],
    )

    system_prompt = SYSTEM
    if args.system_prompt:
        # Check if it's a file
        p = Path(args.system_prompt)
        if p.exists() and p.is_file():
            system_prompt = p.read_text(encoding="utf-8")
        else:
            system_prompt = args.system_prompt

    out = call_text(
        model=args.text_model,
        system_prompt=system_prompt,
        user_prompt=user,
        temperature=0.15,
        max_output_tokens=args.max_output_tokens,
    )
    _, tex = split_output(out)

    (lecture_dir / "lecture_notes.tex").write_text(tex + "\n", encoding="utf-8")
    print(f"[ok] wrote {lecture_dir/'lecture_notes.tex'}")


if __name__ == "__main__":
    main()
