
from __future__ import annotations
import subprocess
from pathlib import Path
import shutil
import abc
import sys
from util import pdf_utils

def run_cmd(cmd: list[str]) -> None:
    print("[run]", " ".join(cmd))
    subprocess.check_call(cmd)

class InputHandler(abc.ABC):
    def __init__(self, input_file: Path, out_root: Path, scripts_root: Path):
        self.input_file = input_file
        self.out_root = out_root
        self.scripts_root = scripts_root
        self.lec_dir_name = self._get_lecture_dir_name()
        self.out_dir = self.out_root / self.lec_dir_name

    def _get_lecture_dir_name(self) -> str:
        # Simplistic naming: use stem
        # You could replicate the 'extract_lecture_number' logic if needed
        return self.input_file.stem

    @abc.abstractmethod
    def process(self, args) -> None:
        """Run the full pipeline for this input file."""
        pass

class PptxHandler(InputHandler):
    def process(self, args) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. pptx2md
        cmd = [sys.executable, str(self.scripts_root / "convert_with_pptx2md.py"), "--pptx", str(self.input_file), "--out_dir", str(self.out_dir)]
        if args.disable_notes:
            cmd.append("--disable_notes")
        run_cmd(cmd)

        # 2. render slides (PNGs)
        # We assume render_slides.py is concurrency-safe here or managed by caller if paralellizing
        run_cmd([sys.executable, str(self.scripts_root / "render_slides.py"), "--pptx", str(self.input_file), "--out_dir", str(self.out_dir), "--dpi", str(args.dpi)])

        # 3. build slides.json
        self._build_lecture_input(args)

        # 4. caption images
        self._caption_images(args)

        # 5. summarize
        self._summarize(args)

    def _build_lecture_input(self, args):
        bli_cmd = [sys.executable, str(self.scripts_root / "build_lecture_input.py"), "--lecture_dir", str(self.out_dir)]
        if args.glitch_fix_with_png:
            bli_cmd.append("--glitch_fix_with_png")
        if args.glitch_fix_model:
            bli_cmd.extend(["--glitch_fix_model", args.glitch_fix_model])
        # ... add other args as needed, mirroring run_all.py ...
        run_cmd(bli_cmd)

    def _caption_images(self, args):
        cmd = [sys.executable, str(self.scripts_root / "caption_images.py"), "--lecture_dir", str(self.out_dir)]
        if args.caption_slide_pngs:
            cmd.append("--caption_slide_pngs")
        run_cmd(cmd)

    def _summarize(self, args):
        cmd = [sys.executable, str(self.scripts_root / "summarize_lecture.py"), "--lecture_dir", str(self.out_dir)]
        if args.system_prompt:
             cmd.extend(["--system_prompt", args.system_prompt])
        run_cmd(cmd)


class PdfHandler(InputHandler):
    def process(self, args) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Extract Text -> slides.md
        print(f"[info] Extracting text from PDF: {self.input_file}")
        slides = pdf_utils.extract_text_from_pdf(self.input_file)
        md_path = self.out_dir / "slides.md"
        pdf_utils.write_slides_md(slides, md_path)
        
        # 2. Render PDF to PNGs (using existing render_slides logic, but adapted)
        # render_slides.py expects a PPTX usually, but has pdf_to_pngs function.
        # We can just call `pdftoppm` directly or reuse a script. 
        # For simplicity, let's call a shell command or a small helper if render_slides is too tied to PPTX.
        # Actually render_slides.py takes --pptx. We might need to modify it or just run pdftoppm here.
        # Let's run pdftoppm directly here or refactor render_slides. 
        # To avoid modifying render_slides heavily, I'll implement image rendering here.
        
        slides_png_dir = self.out_dir / "slides_png"
        slides_png_dir.mkdir(parents=True, exist_ok=True)
        
        # We need pdftoppm
        # Assuming it's installed as per repo instructions
        cmd = ["pdftoppm", "-png", "-r", str(args.dpi), str(self.input_file), str(slides_png_dir / "slide")]
        run_cmd(cmd)
        
        # Rename output slide-01.png -> slide01.png
        for p in sorted(slides_png_dir.glob("slide-*.png")):
            # pdftoppm outputs slide-1.png, slide-10.png
            # We want slide01.png, slide10.png
            # Extract number
            try:
                # name is like slide-1.png
                parts = p.stem.split("-") # ["slide", "1"]
                idx = int(parts[-1])
                new_name = f"slide{idx:02d}.png"
                p.rename(slides_png_dir / new_name)
            except Exception as e:
                print(f"[warn] failed to rename {p}: {e}")

        # 3. build slides.json
        # Reuse PptxHandler's method or duplicate
        # It's the same script usage
        PptxHandler._build_lecture_input(self, args)

        # 4. caption images
        # PDF might not have extracted images in 'img/' folder unless we extract them.
        # pymupdf can extract images. For now, we might only have slide PNGs.
        # So we should enable caption_slide_pngs by default or strictly use that.
        # We'll run the command, but it might not find 'extracted_images'.
        PptxHandler._caption_images(self, args)

        # 5. summarize
        PptxHandler._summarize(self, args)
