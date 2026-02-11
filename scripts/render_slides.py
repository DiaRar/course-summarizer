from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed:\n{' '.join(cmd)}\n\nSTDOUT:\n{p.stdout}\n\nSTDERR:\n{p.stderr}"
        )


def ensure_bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"Missing '{name}'. Install it and ensure it's on PATH.\n"
            f"macOS: brew install --cask libreoffice; brew install poppler"
        )
    return path


def pptx_to_pdf(pptx: Path, out_pdf: Path) -> None:
    soffice = ensure_bin("soffice")
    out_dir = out_pdf.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx)])

    produced = out_dir / (pptx.stem + ".pdf")
    if not produced.exists():
        raise RuntimeError(f"LibreOffice did not produce expected PDF: {produced}")
    produced.replace(out_pdf)


def pdf_to_pngs(pdf: Path, out_dir: Path, dpi: int = 200) -> None:
    pdftoppm = ensure_bin("pdftoppm")
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "slide"

    run([pdftoppm, "-png", "-r", str(dpi), str(pdf), str(prefix)])

    produced = sorted(out_dir.glob("slide-*.png"))
    if not produced:
        raise RuntimeError(f"No PNGs produced in {out_dir}")

    for p in produced:
        idx = int(p.stem.split("-")[-1])
        target = out_dir / f"slide{idx:02d}.png"
        p.replace(target)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pptx", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    pptx = Path(args.pptx)
    out_dir = Path(args.out_dir)
    slides_dir = out_dir / "slides_png"
    tmp_pdf = out_dir / "_tmp.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    pptx_to_pdf(pptx, tmp_pdf)
    pdf_to_pngs(tmp_pdf, slides_dir, dpi=args.dpi)
    tmp_pdf.unlink(missing_ok=True)

    print(f"[ok] rendered slide PNGs -> {slides_dir}")


if __name__ == "__main__":
    main()
