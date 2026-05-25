"""
Test OpenRouter API connectivity using the openai Python SDK
(OpenRouter is fully OpenAI-compatible).
"""
import sys
import io

# Force UTF-8 output so Unicode chars print correctly on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import importlib, subprocess
try:
    importlib.import_module("openai")
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "openai"])

from openai import OpenAI

OPENROUTER_API_KEY = "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"
MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

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
        print(f"\n\n--- Usage ---")
        print(f"Prompt tokens:     {chunk.usage.prompt_tokens}")
        print(f"Completion tokens: {chunk.usage.completion_tokens}")
        print(f"Total tokens:      {chunk.usage.total_tokens}")

print("\n\nOPENROUTER CONNECTION OK!")
print(f"Model used: {MODEL}")
