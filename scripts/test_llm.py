
import os
from dotenv import load_dotenv
load_dotenv()

from llm_client import call_text, ModelConfig

# Force debug print
print(f"DEBUG: OPENROUTER_KEY present: {bool(os.environ.get('OPENROUTER_API_KEY'))}")
print(f"DEBUG: OPENAI_KEY present: {bool(os.environ.get('OPENAI_API_KEY'))}")
print(f"DEBUG: BASE_URL: {os.environ.get('OPENAI_BASE_URL')}")

try:
    print("Testing call_text...")
    resp = call_text(
        system_prompt="You are a test bot.",
        user_prompt="Say hello!",
        model=ModelConfig().text_model,
        max_output_tokens=50
    )
    print(f"Response: {resp}")
except Exception as e:
    print(f"Error: {e}")
