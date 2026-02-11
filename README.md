# Course Summarizer

A powerful, modular pipeline for converting academic course materials (PPTX slides and PDF documents) into coherent, textbook-style summaries using Large Language Models (LLMs).

Built with **LangChain**, **OpenRouter**, and **Google Gemini**, this tool automates the process of extracting text, rendering slides, captioning visuals, and synthesizing comprehensive lecture notes in LaTeX format.

## 🚀 Features

-   **Multi-Format Support**: Seamlessly processes both PowerPoint (`.pptx`) and PDF (`.pdf`) lecture slides.
-   **Intelligent Extraction**:
    -   Extracts text and speaker notes.
    -   Renders high-quality slide images using `pdftoppm` (for PDF) and LibreOffice (for PPTX).
    -   **AI-Powered Captioning**: Uses Vision models (Gemini 3 Flash) to describe complex diagrams and charts.
    -   **Glitch Fixing**: Automatically repairs broken text or OCR errors using LLMs.
-   **Modular Architecture**: Extensible design with dedicated handlers for different input formats.
-   **Academic Synthesis**:
    -   Generates structured, exam-grade LaTeX notes.
    -   Infers course structure (Chapters/Parts) from lecture content.
    -   Generalizable prompts suitable for any subject (CS, Finance, Science, etc.).
-   **Cost-Effective**: Optimized for **OpenRouter** and **Google Gemini 3 Flash** for high speed and low cost.

## 🛠️ Prerequisites

Ensure you have the following installed on your system:

-   **Python 3.10+**
-   **uv** (recommended for dependency management)
-   **LibreOffice** (for PPTX conversion): `brew install --cask libreoffice` (macOS)
-   **Poppler** (for PDF rendering): `brew install poppler` (macOS)

## 📦 Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/course_summarizer.git
    cd course_summarizer
    ```

2.  **Install dependencies using uv**:
    ```bash
    uv venv
    source .venv/bin/activate
    uv pip install -r requirements.txt
    ```
    *(Note: If `requirements.txt` is missing, basic dependencies are: `langchain langchain-openai pymupdf python-dotenv pptx2md-diar`)*

3.  **Set up Configuration**:
    Create a `.env` file in the root directory:
    ```bash
    OPENROUTER_API_KEY=sk-or-your-api-key-here
    # Optional: Override base URL if not using OpenRouter default
    # OPENAI_BASE_URL=https://openrouter.ai/api/v1
    ```

## 🏃 Usage

### Basic Usage

Place your lecture files (PPTX or PDF) in a `lectures/` directory and run:

```bash
python scripts/process_course.py --lectures_dir lectures --out_root out
```

This will:
1.  Scan `lectures/` for `.pptx` and `.pdf` files.
2.  Process each file: extract text, render images, caption visuals, and summarize.
3.  Output processed content to `out/<lecture_name>/`.
4.  Run structure inference and synthesized course note generation.

### Advanced Options

```bash
python scripts/process_course.py \
  --lectures_dir lectures \
  --out_root out \
  --limit 2 \                       # Process only the first 2 lectures
  --max_workers 4 \                 # Parallel processing
  --system_prompt "You are a physics tutor." \ # Custom persona
  --no-caption-slide-pngs \         # Disable AI image captioning
  --no-glitch-fix-with-png          # Disable OCR correction
```

### Full Pipeline breakdown

1.  **Ingestion**: `process_course.py` detects file type.
2.  **Conversion**:
    -   **PPTX**: Converted to Markdown via `pptx2md`. Slides rendered to PNG via LibreOffice.
    -   **PDF**: Text extracted via `pymupdf`. Slides rendered to PNG via `pdftoppm`.
3.  **Enhancement**:
    -   **Glitch Fix**: Broken text is repaired using `glitch_fix_model` (Default: Gemini 3 Flash).
    -   **Captioning**: Slide images are analyzed by `glitch_fix_vision_model` to generate descriptions.
4.  **Summarization**: Each lecture is summarized into `lecture_notes.tex`.
5.  **Synthesis**:
    -   `infer_structure.py`: Analyzes all processed lectures to determine chapter order and hierarchy.
    -   `synthesize_course.py`: Compiles a master `course_notes.tex` document with a global glossary and unified structure.

## 📂 Project Structure

```
course_summarizer/
├── lectures/               # Input directory (PPTX/PDF)
├── out/                    # Output directory
│   ├── Lecture1/           # Per-lecture artifacts
│   │   ├── slides.md       # Raw text
│   │   ├── slides_png/     # Rendered images
│   │   ├── captions.json   # AI Captions
│   │   └── lecture_notes.tex
│   └── synthesized/        # Final course output
│       ├── structure.json
│       └── course_notes.tex
├── scripts/
│   ├── process_course.py   # Main entry point
│   ├── handlers.py         # Format-specific logic (PDF/PPTX)
│   ├── llm_client.py       # LangChain wrapper for OpenRouter
│   ├── util/               # Helpers (e.g., pdf_utils.py)
│   └── ...                 # Component scripts
└── README.md
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
