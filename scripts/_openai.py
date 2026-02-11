from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI


@dataclass(frozen=True)
class ModelConfig:
    # Pick models you have access to.
    vision_model: str = "gpt-5-nano"
    text_model: str = "gpt-5.2"
    mini_text_model: str = "gpt-5-mini"


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


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


def responses_text(
    *,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.15,
    max_output_tokens: Optional[int] = None,
) -> str:
    client = get_client()
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    return resp.output_text


def responses_vision(
    *,
    model: str,
    system: str,
    user_text: str,
    image_paths: List[str],
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = 400,
) -> str:
    client = get_client()
    content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_text}]
    for p in image_paths:
        content.append({"type": "input_image", "image_url": img_to_data_url(p)})

    request = {
        "model": model,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "max_output_tokens": max_output_tokens,
    }
    if temperature is not None:
        request["temperature"] = temperature

    resp = client.responses.create(**request)
    return resp.output_text
