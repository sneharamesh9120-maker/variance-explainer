"""Step 5: the one place the app talks to the LLM.

Uses Google Gemini by default (free tier). Gemini offers an OpenAI-compatible
endpoint, so the same client code works for both. If GEMINI_API_KEY is not set
but OPENAI_API_KEY is, it falls back to OpenAI.
"""

import os
import time

from openai import OpenAI

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
TIMEOUT_SECONDS = 45


class LLMError(Exception):
    pass


def _client_and_model():
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if gemini_key:
        client = OpenAI(api_key=gemini_key, base_url=GEMINI_BASE_URL,
                        timeout=TIMEOUT_SECONDS, max_retries=1)
        return client, os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    if openai_key:
        client = OpenAI(api_key=openai_key, timeout=TIMEOUT_SECONDS, max_retries=1)
        return client, os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    raise LLMError("No API key found. Add GEMINI_API_KEY in Replit under Secrets.")


def call_llm(messages):
    """Returns dict with text, model, tokens and latency. Raises LLMError on failure."""
    client, model = _client_and_model()
    start = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,  # low, because we want the same answer for the same data
            response_format={"type": "json_object"},
        )
    except Exception as e:  # network, auth, rate limit, timeout
        raise LLMError(f"{type(e).__name__}: {e}") from e

    text = resp.choices[0].message.content or ""
    if not text.strip():
        raise LLMError("The AI returned an empty reply.")
    usage = getattr(resp, "usage", None)
    return {
        "text": text,
        "model": model,
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "latency_ms": int((time.time() - start) * 1000),
    }
