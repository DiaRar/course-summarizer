from typing import Optional
from pathlib import Path
from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class EnvSettings(BaseSettings):
    openrouter_api_key: Optional[str] = Field(None, validation_alias="OPENROUTER_API_KEY")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

_env_loader = EnvSettings()

class Settings(BaseModel):
    # Secrets
    openrouter_api_key: Optional[str] = _env_loader.openrouter_api_key
    
    # Core
    openai_base_url: str = "https://openrouter.ai/api/v1"
    
    # Models
    vision_model: str = "google/gemini-3-flash-preview"
    text_model: str = "google/gemini-3-flash-preview"
    mini_text_model: str = "google/gemini-3-flash-preview"
    
    # Paths
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

settings = Settings()
