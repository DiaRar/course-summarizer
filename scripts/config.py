from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Core
    openai_api_key: Optional[str] = Field(None, validation_alias="OPENAI_API_KEY")
    openrouter_api_key: Optional[str] = Field(None, validation_alias="OPENROUTER_API_KEY")
    openai_base_url: str = Field("https://openrouter.ai/api/v1", validation_alias="OPENAI_BASE_URL")
    
    # Models
    vision_model: str = "google/gemini-2.0-flash-001"
    text_model: str = "google/gemini-2.0-flash-001"
    mini_text_model: str = "google/gemini-2.0-flash-001"
    
    # Paths (defaults, can be overridden by CLI args usually)
    lectures_dir: Path = Path("lectures")
    out_root: Path = Path("out")
    
    # Processing
    max_workers: int = 4
    dpi: int = 200
    caption_slide_pngs: bool = True
    
    # Glitch Fix
    glitch_fix_with_png: bool = True
    glitch_fix_batch_size: int = 5
    
    # Rewrite
    rewrite_max_output_tokens: int = 1200
    
    # Synthesis
    synthesis_max_output_tokens: int = 500000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
