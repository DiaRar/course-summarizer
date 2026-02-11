from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Tuple

from llm_client import ModelConfig, call_text


SYSTEM = """You synthesize full academic course notes in LaTeX.
You are strict about notation consistency and remove redundancy.
You keep math correct and exam-useful.
You keep key figures where helpful (referencing the existing embedded images in the lecture notes)."""

PROMPT = """You are given multiple lecture notes (LaTeX), already containing figure references/tables.
Synthesize them into coherent course notes organized by Chapter (and Parts if present).

Requirements:
- Group by chapter headings.
- Normalize notation and INCLUDE a complete Global Glossary at the start defining every symbol you use.
- MUST define at least these symbols (extend if others appear): PV, FV, NPV, IRR, MIRR, PI, WACC, EAA, CA, CL, NWC, NFA, EBIT, EBT, NI, Dep, OCF, FCF, CFFA, BV, MV, ROE, ROA, PM (profit margin), TIE, DSO/DSI/Inv turnover/Receivables turnover/TAT, Beta, RP, rf, k, r, g, D, E, P0, D0/D1, TV/terminal value, HV, CF, ΔNWC, NCS/CapEx, Tax shield, EPS, payout, b (retention), D/E, EM (equity multiplier), sigma/Var/Cov/rho.
- Avoid duplication across Part A/B.
- Keep key figures/tables when they are essential; do not include every single slide image.
- Preserve as much textual content as possible; do NOT aggressively summarize. Only deduplicate verbatim repeats across lectures; keep explanations, bullets, and formulas intact.
- Maintain similar length to the source corpus; do not shorten sections beyond light de-duplication.
- Produce LaTeX only.

Output format EXACTLY:

=== LATEX ===
<latex>

Structure:
{structure_json}

Lecture notes corpus:
{notes}
"""


def split_output(text: str) -> Tuple[str, str]:
    tx_tag = "=== LATEX ==="
    if tx_tag not in text:
        return "", text.strip()
    tx = text.split(tx_tag, 1)[1].strip()
    return "", tx


def _rewrite_paths(tex: str, base_prefix: str) -> str:
    # Make image paths unique by prefixing with lecture dir relative to compile cwd.
    def repl(m: re.Match) -> str:
        prefix = m.group(1)
        rest = m.group(2)
        return "{" + base_prefix + prefix + rest

    # Only rewrite bare img/ or slides_png/ (not already prefixed)
    tex = re.sub(r"\{(img/)([^}]+)", repl, tex)
    tex = re.sub(r"\{(slides_png/)([^}]+)", repl, tex)
    return tex


def read_notes(out_root: Path, ordered_dirs: List[str], prefix_override: str | None) -> str:
    chunks = []
    for d in ordered_dirs:
        p = out_root / d / "lecture_notes.tex"
        if p.exists():
            tex = p.read_text(encoding="utf-8")
            if prefix_override is not None:
                base_prefix = prefix_override.rstrip("/") + "/" + d + "/"
            else:
                base_prefix = str((out_root / d).as_posix()) + "/"
            tex = _rewrite_paths(tex, base_prefix)
            chunks.append(f"\n\n% SOURCE: {d}\n\n" + tex)
    return "\n".join(chunks)


def build_ordered_dirs(structure: dict) -> List[str]:
    ordered: List[str] = []
    for ch in structure["chapters"]:
        for part in ch["parts"]:
            ordered.extend(part["files"])
    return ordered


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_root", default="out")
    ap.add_argument("--include_graphics_prefix", default=None, help="optional path prefix for \\includegraphics (e.g., '../Lecture1')")
    ap.add_argument("--text_model", default=ModelConfig().text_model)
    ap.add_argument("--max_output_tokens", type=int, default=500000)
    args = ap.parse_args()

    out_root = Path(args.out_root)
    struct_path = out_root / "synthesized" / "structure.json"
    if not struct_path.exists():
        raise RuntimeError("Missing structure.json. Run infer_structure.py first.")

    structure = json.loads(struct_path.read_text(encoding="utf-8"))

    # Determine a stable ordered list of lecture dirs based on chapters/parts
    ordered: List[str] = build_ordered_dirs(structure)

    notes = read_notes(out_root, ordered, args.include_graphics_prefix)
    struct_json_full = json.dumps(structure, indent=2)
    notes_len = len(notes)
    struct_len = len(struct_json_full)
    print(f"[info] structure.json chars={struct_len}, notes chars={notes_len}")

    user = PROMPT.format(
        structure_json=struct_json_full[:120000],
        notes=notes[:400000],
    )

    out = call_text(
        model=args.text_model,
        system_prompt=SYSTEM,
        user_prompt=user,
        temperature=0.05,
        max_output_tokens=args.max_output_tokens,
    )
    # Include cross-reference metadata if present
    # We pass structure JSON as-is; if parts/files carry also_relates_to, the model can use it.
    _, tex = split_output(out)

    synth_dir = out_root / "synthesized"
    synth_dir.mkdir(parents=True, exist_ok=True)
    (synth_dir / "course_notes.tex").write_text(tex + "\n", encoding="utf-8")
    print(f"[ok] wrote {synth_dir/'course_notes.tex'}")


if __name__ == "__main__":
    main()
