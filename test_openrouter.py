"""
Test OpenRouter API connectivity using the openai Python SDK
(OpenRouter is fully OpenAI-compatible).
"""
import io
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

# Force UTF-8 output so Unicode chars print correctly on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

if not OPENROUTER_API_KEY:
    print("OPENROUTER_API_KEY is missing. Add it to .env or your environment.")
    raise SystemExit(1)

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "https://github.com/george-job-agent",
        "X-Title": "George Job Agent",
    }
)

print(f"Testing OpenRouter -> {MODEL}\n")
print("Prompt: How many r's are in the word 'strawberry'?\n")
print("Response: ", end="", flush=True)

stream = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "user", "content": "How many r's are in the word 'strawberry'? Count carefully."}
    ],
    stream=True,
    stream_options={"include_usage": True}
)

response_text = ""
for chunk in stream:
    content = chunk.choices[0].delta.content if chunk.choices else None
    if content:
        response_text += content
        print(content, end="", flush=True)
    if hasattr(chunk, "usage") and chunk.usage:
        print("\n\n--- Usage ---")
        print(f"Prompt tokens:     {chunk.usage.prompt_tokens}")
        print(f"Completion tokens: {chunk.usage.completion_tokens}")
        print(f"Total tokens:      {chunk.usage.total_tokens}")

print("\n\nOPENROUTER CONNECTION OK!")
print(f"Model used: {MODEL}")
