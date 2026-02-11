
from __future__ import annotations

import os
import base64
from typing import List, Optional, Any
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from dotenv import load_dotenv

# Load env from .env file if present
load_dotenv()

@dataclass(frozen=True)
class ModelConfig:
    # Default models - using Google Gemini 3 Flash via OpenRouter as requested
    vision_model: str = "google/gemini-3-flash-preview" 
    text_model: str = "google/gemini-3-flash-preview"
    mini_text_model: str = "google/gemini-3-flash-preview" # fast fallback

def get_chat_model(model_name: str, temperature: float = 0.1, max_tokens: Optional[int] = None) -> ChatOpenAI:
    """
    Returns a configured ChatOpenAI instance.
    Supports OpenRouter via OPENAI_BASE_URL + OPENAI_API_KEY (or OPENROUTER_API_KEY).
    """
    
    # LangChain's ChatOpenAI automatically looks for OPENAI_API_KEY and OPENAI_BASE_URL.
    # To support OpenRouter explicitly if the user set OPENROUTER_API_KEY but not OPENAI_API_KEY:
    # We prefer OPENROUTER_API_KEY if present, as we default to OpenRouter URL.
    api_key = os.environ.get("OPENROUTER_API_KEY")
    # Force OpenRouter URL
    base_url = "https://openrouter.ai/api/v1"
    
    if not api_key:
        raise ValueError("Missing API Key. Please set OPENROUTER_API_KEY in your .env file.")

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
        base_url=base_url,
        default_headers={
            "HTTP-Referer": "https://github.com/your-repo/course-summarizer", # Optional: Change to your site
            "X-Title": "Course Summarizer",
        }
    )

def img_to_data_url(path: str) -> str:
    ext = path.lower().split(".")[-1]
    if ext in ("jpg", "jpeg"):
        mime = "image/jpeg"
    elif ext in ("png", "webp"):
        mime = f"image/{ext}"
    else:
        mime = "application/octet-stream"

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def call_text(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.15,
    max_output_tokens: Optional[int] = None,
) -> str:
    """
    Synchronous text-only call.
    """
    chat = get_chat_model(model, temperature, max_output_tokens)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    response = chat.invoke(messages)
    return str(response.content)

def call_vision(
    system_prompt: str,
    user_text: str,
    image_paths: List[str],
    model: str,
    temperature: float = 0.15,
    max_output_tokens: Optional[int] = 400,
) -> str:
    """
    Synchronous vision call.
    """
    chat = get_chat_model(model, temperature, max_output_tokens)
    
    # Construct content list for HumanMessage
    content: List[dict] = [{"type": "text", "text": user_text}]
    for p in image_paths:
        data_url = img_to_data_url(p)
        content.append({
            "type": "image_url", 
            "image_url": {"url": data_url}
        })
        
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=content),
    ]
    
    response = chat.invoke(messages)
    return str(response.content)
