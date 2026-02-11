from __future__ import annotations

import argparse
import concurrent.futures
import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Tuple

from tqdm import tqdm

from _openai import ModelConfig, responses_vision

ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


SYSTEM = """You create concise, precise, finance-safe captions (2–3 sentences).
State what is visible: chart axes/shape, table comparisons, cashflow timing/signs.
Do not speculate beyond the image + provided slide context."""

USER_TEMPLATE = """Write a concise technical caption (2–3 sentences) for this visual.

Slide title: {title}

Nearby slide content (Markdown, may include formulas/tables):
{body_md}

Requirements:
- 2–3 sentences max
- If timeline/cashflows: specify time points and sign convention
- If chart: specify axes and key relationship direction/shape
- If table: what it compares + what varies across rows/cols
- Mention key finance terms if present (NPV, IRR, CAPM, WACC, duration, convexity, etc.)
- Do not add information not visible in the image/context
"""


def load_slides(slides_json: Path) -> List[dict]:
    return json.loads(slides_json.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lecture_dir", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--vision_model", default=ModelConfig().vision_model)
    ap.add_argument("--caption_slide_pngs", action="store_true", help="also caption full slide PNG renders")
    ap.add_argument(
        "--caption_max_output_tokens",
        type=int,
        default=3000,
        help="max tokens for each caption response",
    )
    ap.add_argument(
        "--caption_retry",
        type=int,
        default=2,
        help="number of additional attempts with the primary model if caption is empty",
    )
    ap.add_argument(
        "--caption_fallback_model",
        default=None,
        help="optional fallback vision model if primary model returns empty/error",
    )
    ap.add_argument(
        "--caption_workers",
        type=int,
        default=16,
        help="number of parallel caption requests (respect your rate limits)",
    )
    ap.add_argument(
        "--caption_rate_limit_rps",
        type=float,
        default=0.0,
        help="approximate requests per second cap (per process) to the vision API",
    )
    args = ap.parse_args()

    lecture_dir = Path(args.lecture_dir)
    slides_path = lecture_dir / "slides.json"
    if not slides_path.exists():
        raise RuntimeError("Missing slides.json. Run build_lecture_input.py first.")

    slides = load_slides(slides_path)
    captions_path = lecture_dir / "captions.json"
    captions: Dict[str, str] = {}
    if captions_path.exists():
        captions = json.loads(captions_path.read_text(encoding="utf-8"))

    jobs: List[tuple[str, str, str]] = []
    # (key, image_abs_path, user_prompt)
    for s in slides:
        title = s.get("title", "")
        body = (s.get("body_md", "") or "")[:8000]

        # exported images
        for rel in s.get("extracted_images", []) or []:
            key = rel
            if (not args.force) and key in captions:
                continue
            img_abs = lecture_dir / rel
            if img_abs.suffix.lower() not in ALLOWED_SUFFIXES:
                print(f"[skip] unsupported image type for captioning: {img_abs.name}")
                continue
            jobs.append((key, str(img_abs), USER_TEMPLATE.format(title=title, body_md=body)))

        # slide PNG fallback (optional)
        if args.caption_slide_pngs:
            rel = s.get("slide_png", "")
            if rel:
                key = rel
                if (not args.force) and key in captions:
                    continue
                img_abs = lecture_dir / rel
                if img_abs.suffix.lower() not in ALLOWED_SUFFIXES:
                    print(f"[skip] unsupported image type for captioning: {img_abs.name}")
                    continue
                jobs.append((key, str(img_abs), USER_TEMPLATE.format(title=title, body_md=body)))

    if not jobs:
        print("[ok] nothing to caption")
        return

    print(f"[info] caption jobs: {len(jobs)}, workers={args.caption_workers}")

    write_lock = threading.Lock()
    rate_lock = threading.Lock()
    last_request_ts = 0.0

    def caption_one(job: Tuple[str, str, str]) -> Tuple[str, str]:
        key, img_abs, prompt = job
        p = Path(img_abs)
        if not p.exists():
            return key, "[missing image]"

        models_to_try = [args.vision_model]
        if args.caption_fallback_model:
            models_to_try.append(args.caption_fallback_model)

        cap: str | None = None
        last_err = None

        for mi, model in enumerate(models_to_try):
            attempts = 1 + (args.caption_retry if mi == 0 else 0)
            for attempt in range(attempts):
                # crude per-process rate limit if enabled
                if args.caption_rate_limit_rps > 0:
                    with rate_lock:
                        nonlocal last_request_ts
                        now = time.time()
                        min_interval = 1.0 / max(0.1, args.caption_rate_limit_rps)
                        sleep_for = last_request_ts + min_interval - now
                        if sleep_for > 0:
                            time.sleep(sleep_for)
                        last_request_ts = time.time()

                try:
                    resp = responses_vision(
                        model=model,
                        system=SYSTEM,
                        user_text=prompt,
                        image_paths=[img_abs],
                        max_output_tokens=args.caption_max_output_tokens,
                    ).strip()
                    if resp:
                        cap = resp
                        break
                    else:
                        last_err = "empty caption"
                except Exception as e:
                    last_err = str(e)
                if cap:
                    break
            if cap:
                break

        if not cap:
            msg = f"[caption error: {last_err or 'unknown'}]"
            print(f"[error] {key}: {msg}")
            cap = msg
        return key, cap

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.caption_workers)) as ex:
        for key, cap in tqdm(ex.map(caption_one, jobs), total=len(jobs), desc="captioning"):
            with write_lock:
                captions[key] = cap
                captions_path.write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[ok] wrote {captions_path} (parallel)")


if __name__ == "__main__":
    main()
