# Course Summarizer

This project is a tool to synthesize coherent academic course notes from raw lecture materials (LaTeX slides/notes) using LLMs. It structures, deduplicates, and refines the content into a single unified LaTeX document.

## Features

- **Structure Inference**: Automatically infers the course structure (Chapters/Parts) from lecture folders (`infer_structure.py`).
- **Content Synthesis**: Uses an LLM (e.g., Claude 3.5 Sonnet) to merge and rewrite lecture notes into a consistent textbook-style format (`synthesize_course.py`).
- **LaTeX & Graphics**: Preserves mathematical notation and handles image inclusions properly.

## Usage

1.  **Prepare Input**: Place your lecture outputs in the `out/` directory (or configure `out_root`).
2.  **Infer Structure**:
    ```bash
    python scripts/infer_structure.py
    ```
    This generates `out/synthesized/structure.json`.
3.  **Synthesize Notes**:
    ```bash
    python scripts/synthesize_course.py
    ```
    This reads the structure and lecture notes, sending them to the LLM to generate `out/synthesized/course_notes.tex`.

## Dependencies

- Python 3.x
- `llm_client` (internal module)
- `pylatexenc` (likely used for Latex parsing)

## Configuration

- `.env`: API keys for LLM provider.
- `model`: Configured via command line args.
