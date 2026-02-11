from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional

from _openai import ModelConfig, responses_text


CHAPTER_PATS = [
    re.compile(r"\bchapter\s*(\d+)\b", re.I),
    re.compile(r"\bch\.?\s*(\d+)\b", re.I),
    re.compile(r"\bch(\d+)\b", re.I),
]


def extract_chapter(s: str) -> Optional[int]:
    s = (s or "").strip()
    for pat in CHAPTER_PATS:
        m = pat.search(s)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
    return None


def norm_title(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\bchapter\s*\d+\b", "", s)
    s = re.sub(r"\bch\.?\s*\d+\b", "", s)
    s = re.sub(r"\bch\d+\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:140]


def read_titles_from_slides_md(md_path: Path) -> List[str]:
    if not md_path.exists():
        return []
    titles = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            t = line.lstrip("#").strip()
            if t:
                titles.append(t)
    return titles


def extract_lecture_number(name: str) -> int:
    m = re.search(r"lecture\s*(\d+)", name, flags=re.I)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    return 10**9


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_root", default="out")
    ap.add_argument("--llm_grouping", action="store_true", help="use LLM to infer chapter/topic per lecture")
    ap.add_argument("--text_model", default=ModelConfig().text_model, help="LLM model for grouping when --llm_grouping is set")
    ap.add_argument("--sample_chars", type=int, default=3000, help="chars of slides.md to sample for LLM grouping")
    args = ap.parse_args()

    out_root = Path(args.out_root)
    lecture_dirs = sorted(
        [d for d in out_root.iterdir() if d.is_dir() and (d / "slides.md").exists()],
        key=lambda d: (extract_lecture_number(d.name), d.name),
    )

    def llm_label(dir_path: Path) -> tuple[list[int], str]:
        if not args.llm_grouping:
            return [], ""
        md_path = dir_path / "slides.md"
        try:
            md_sample = md_path.read_text(encoding="utf-8")[: args.sample_chars]
        except Exception:
            return [], ""
        prompt = (
            "You are given a sample of lecture slides.\n"
            "Return a JSON object with fields:\n"
            '{ "chapters": [<integers>], "topic": "<concise topic string>" }\n'
            "Use the slide content to infer the primary and secondary chapter numbers (if present) and topic/title.\n"
            "Do not add extra text.\n\n"
            f"Slides sample:\n{md_sample}"
        )
        try:
            raw = responses_text(
                model=args.text_model,
                system="You label finance lectures by chapter number and topic.",
                user=prompt,
                temperature=0.0,
                max_output_tokens=200,
            ).strip()
            obj = json.loads(raw)
            chapters_raw = obj.get("chapters", [])
            chapters: list[int] = []
            if isinstance(chapters_raw, list):
                for c in chapters_raw:
                    try:
                        if isinstance(c, str):
                            c = re.findall(r"\d+", c)[0]
                        chapters.append(int(c))
                    except Exception:
                        continue
            topic = obj.get("topic", "") or ""
            return chapters, topic.strip()
        except Exception:
            return [], ""

    file_info = []
    for d in lecture_dirs:
        titles = read_titles_from_slides_md(d / "slides.md")
        chapters = [c for c in (extract_chapter(t) for t in titles) if c is not None]
        dominant_ch = Counter(chapters).most_common(1)[0][0] if chapters else None
        secondary_ch: list[int] = []
        topic = Counter([norm_title(t) for t in titles if t]).most_common(1)[0][0] if titles else ""
        if args.llm_grouping:
            llm_chs, llm_topic = llm_label(d)
            if llm_chs:
                dominant_ch = llm_chs[0]
                secondary_ch = llm_chs[1:]
            if llm_topic:
                topic = llm_topic
        file_info.append(
            {
                "dir": d.name,
                "chapter": dominant_ch,
                "also_relates_to": secondary_ch,
                "topic": topic,
                "titles_sample": titles[:20],
            }
        )

    by_ch = defaultdict(list)
    for f in file_info:
        key = f["chapter"] if f["chapter"] is not None else "unknown"
        by_ch[key].append(f)

    chapters_out = []
    for ch, files in sorted(by_ch.items(), key=lambda x: (9999 if x[0] == "unknown" else int(x[0]))):
        files_sorted = sorted(files, key=lambda x: x["dir"])
        parts = []
        used = set()
        for i, f in enumerate(files_sorted):
            if f["dir"] in used:
                continue
            part_files = [f["dir"]]
            used.add(f["dir"])

            # Pair A/B: adjacent file with same chapter and similar normalized topic prefix
            if i + 1 < len(files_sorted):
                g = files_sorted[i + 1]
                if g["dir"] not in used:
                    if (f["topic"] and g["topic"] and f["topic"][:30] == g["topic"][:30]):
                        part_files.append(g["dir"])
                        used.add(g["dir"])

            parts.append({"files": part_files, "label": "A+B" if len(part_files) == 2 else "single"})
        chapters_out.append({"chapter": ch, "parts": parts})

    out_dir = out_root / "synthesized"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {"files": file_info, "chapters": chapters_out}
    (out_dir / "structure.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[ok] wrote {out_dir/'structure.json'}")


if __name__ == "__main__":
    main()
