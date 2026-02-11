import shutil
import subprocess
from pathlib import Path
from typing import List

def run_cmd(cmd: List[str]) -> None:
    """Run a subprocess command and check for errors."""
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}") from e

def ensure_bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Missing '{name}'. Please install it.")
    return path

def pptx_to_pdf(pptx: Path, out_pdf: Path) -> None:
    soffice = ensure_bin("soffice")
    out_dir = out_pdf.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # libreoffice converts to name.pdf in outdir
    run_cmd([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx)])

    produced = out_dir / (pptx.stem + ".pdf")
    if not produced.exists():
        raise RuntimeError(f"LibreOffice failed to produce {produced}")
    
    if produced != out_pdf:
        produced.replace(out_pdf)

def pdf_to_pngs(pdf: Path, out_dir: Path, dpi: int = 200) -> None:
    pdftoppm = ensure_bin("pdftoppm")
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "slide"

    run_cmd([pdftoppm, "-png", "-r", str(dpi), str(pdf), str(prefix)])

    produced = sorted(out_dir.glob("slide-*.png"))
    if not produced:
        raise RuntimeError(f"No PNGs produced in {out_dir}")

    for p in produced:
        # slide-01.png or slide-1.png -> slide01.png
        try:
            parts = p.stem.split("-")
            idx = int(parts[-1])
            target = out_dir / f"slide{idx:02d}.png"
            p.replace(target)
        except ValueError:
            continue

def latex_to_pdf(tex_file: Path, out_dir: Path = None, clean: bool = True) -> Path:
    """
    Compiles a LaTeX file to PDF.
    Returns the path to the generated PDF.
    """
    if out_dir is None:
        out_dir = tex_file.parent
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Try latexmk first, fallback to pdflatex
    compiler = shutil.which("latexmk")
    if compiler:
        cmd = [compiler, "-pdf", "-interaction=nonstopmode", f"-output-directory={out_dir}", str(tex_file)]
    else:
        compiler = ensure_bin("pdflatex")
        cmd = [compiler, "-interaction=nonstopmode", f"-output-directory={out_dir}", str(tex_file)]
        
    # Run compilation
    print(f"[info] Compiling {tex_file.name}...")
    run_cmd(cmd)
    
    # Expected PDF name
    pdf_path = out_dir / (tex_file.stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"PDF compilation failed for {tex_file}")

    if clean:
        # Cleanup aux files
        for ext in [".aux", ".log", ".out", ".toc", ".fls", ".fdb_latexmk"]:
            f = out_dir / (tex_file.stem + ext)
            if f.exists():
                f.unlink()
                
    return pdf_path
