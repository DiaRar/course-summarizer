# Course Summarizer

A production-ready, modular pipeline for converting academic course materials (PPTX, PDF) into coherent, textbook-style summaries using LLMs.

Built with **LangChain**, **Pydantic**, and **Google Gemini** (via OpenRouter), automating the process from slide extraction to LaTeX synthesis and PDF compilation.

## 🚀 Features

-   **Unified CLI**: Single entry point `scripts/main.py` for all operations.
-   **Multi-Format Support**: Processes both `.pptx` and `.pdf` slides.
-   **Intelligent Extraction**:
    -   Extracts text and renders high-quality slide images.
    -   **AI-Powered Glitch Fixing**: Repairs OCR errors and broken math using Vision and Text models.
    -   **Latex Synthesis**: Generates exam-grade LaTeX notes for each lecture and a unified course book.
-   **PDF Compilation**: Automatically compiles generated LaTeX into PDFs (requires `pdflatex` or `latexmk`).
-   **Cleanup**: Option to remove intermediate files (PNGs) to save space.
-   **Incremental Refresh**: Detect new lectures and process only those, while keeping existing outputs and rebuilding the course summary.
-   **Configurable**: Uses `.env` and `scripts/config.py` for easy configuration.

## 🛠️ Prerequisites

-   **Python 3.12+**
-   **LibreOffice** (for PPTX -> PDF conversion):
    -   **macOS**: `brew install --cask libreoffice`
    -   **Windows**: Download and install from [libreoffice.org](https://www.libreoffice.org/download/download/). Ensure `soffice` is in your PATH.
    -   **Linux (Ubuntu/Debian)**: `sudo apt install libreoffice`
-   **Poppler** (for PDF rendering):
    -   **macOS**: `brew install poppler`
    -   **Windows**: Download binary releases (e.g., from [github.com/oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows)), extract, and add the `bin` folder to your PATH.
    -   **Linux (Ubuntu/Debian)**: `sudo apt install poppler-utils`
-   **LaTeX Distribution** (for PDF compilation):
    -   **macOS**: `brew install mactex` or `brew install basictex`
    -   **Windows**: Install [MiKTeX](https://miktex.org/) or [TeX Live](https://www.tug.org/texlive/windows.html). Ensure `pdflatex` is in PATH.
    -   **Linux (Ubuntu/Debian)**: `sudo apt install texlive-latex-base texlive-fonts-recommended texlive-latex-extra`

## 📦 Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/DiaRar/course-summarizer.git
    cd course_summarizer
    ```

2.  **Install dependencies**:
    Using `uv` (recommended):
    ```bash
    uv venv
    source .venv/bin/activate
    uv pip install -r requirements.txt
    ```
    Or standard pip:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuration**:
    Create a `.env` file:
    ```bash
    OPENROUTER_API_KEY=sk-your-key
    ```

## 🏃 Usage

All commands should be run from the **project root** using the module syntax:

### 1. Process Lectures

Scans `lectures/` directory, processes all `.pptx` and `.pdf` files, and generates summaries in `out/`.

```bash
python -m scripts.main process --lectures_dir lectures --out_root out --compile-pdf
```

**Options:**
-   `--compile-pdf`: Compile the final course notes into a PDF.
-   `--clean-intermediate`: Remove intermediate slide images after processing to save space.

### 2. Refresh (Incremental Update)

If new lectures were added to the input directory, `refresh` will process **only the new ones** while keeping existing outputs intact, then rebuild the full course summary:

```bash
python -m scripts.main refresh --lectures_dir lectures --out_root out --compile-pdf
```

A lecture is considered "already processed" if its output directory contains a `lecture_notes.tex` file.

### 3. Synthesize Only

If you have already processed lectures and want to re-run the course synthesis (merging all notes):

```bash
python -m scripts.main synthesize --out_root out --compile-pdf
```

### 4. Clean Output

Removes the entire output directory.

```bash
python -m scripts.main clean --out_root out
```

## 📂 Project Structure

```
course_summarizer/
├── lectures/               # Input directory
├── out/                    # Output directory
├── scripts/
│   ├── main.py             # CLI Entry Point
│   ├── config.py           # Configuration
│   ├── lib/                # Core modules
│   │   ├── content_parser.py
│   │   ├── llm.py
│   │   ├── pdf_tools.py
│   │   ├── summarizer.py
│   │   └── synthesis.py
└── requirements.txt
```

## 🤝 Contributing

Contributions are welcome! Please submit a Pull Request.
