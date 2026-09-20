"""LLM provider service with graceful zero-cost multi-provider fallback.

Provider priority:
  1. Groq (llama-3.3-70b-versatile) — Free tier, fast inference
  2. Google Gemini (gemini-1.5-flash) — Free tier fallback
  3. Ollama CLI (local llama3.2) — Fully local offline fallback (no API key needed)

Implements exponential backoff on 429 rate limit responses and transparently
falls through to the next provider so runs never abort unexpectedly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    OLLAMA_MODEL,
)
from src.utils.errors import LLMProviderError
from src.utils.logging import log_info, log_warning


# ── Groq Provider ─────────────────────────────────────────────────────────────

def _call_groq(system: str, user: str, temperature: float, max_tokens: int) -> str:
    api_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY not configured.")

    from groq import Groq, RateLimitError

    client = Groq(api_key=api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    # Call with tenacity retry on 429
    @retry(
        retry=retry_if_exception_type(RateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        reraise=True,
    )
    def _execute():
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    return _execute()


# ── Gemini Provider ───────────────────────────────────────────────────────────

def _call_gemini(system: str, user: str, temperature: float, max_tokens: int) -> str:
    api_key = os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured.")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    generation_config = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system if system else None,
        generation_config=generation_config,
    )

    resp = model.generate_content(user)
    return resp.text or ""


# ── Ollama Provider (Fully local, no key) ──────────────────────────────────────

def _get_available_ollama_model() -> str:
    if os.getenv("OLLAMA_MODEL"):
        return os.getenv("OLLAMA_MODEL")
    try:
        proc = subprocess.run(
            ["ollama", "list"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        lines = proc.stdout.strip().splitlines()[1:]
        names = [line.split()[0] for line in lines if line.strip()]
        for candidate in ["llama3.1:8b", "llama3.2:latest", "llama3.2", "qwen2.5-coder:1.5b-base", "gemma3:4b"]:
            for name in names:
                if candidate in name:
                    return name
        if names:
            return names[0]
    except Exception:
        pass
    return OLLAMA_MODEL


def _call_ollama(system: str, user: str, temperature: float, max_tokens: int) -> str:
    if not shutil.which("ollama"):
        raise ValueError("Ollama executable not found in PATH.")

    model = _get_available_ollama_model()
    prompt = f"System: {system}\n\nUser: {user}" if system else user
    cmd = ["ollama", "run", model, prompt]

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=True,
        )
        return proc.stdout.strip()
    except Exception as e:
        raise ValueError(f"Ollama local execution ({model}) failed: {e}") from e


# ── Public Unified API ────────────────────────────────────────────────────────

def call_llm(
    system: str = "",
    user: str = "",
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS,
    preferred_provider: Optional[str] = None,
) -> str:
    """Execute LLM call across provider priority chain: Groq -> Gemini -> Ollama.

    Args:
        system: System prompt instruction.
        user: User message or prompt payload.
        temperature: Sampling temperature.
        max_tokens: Output token budget.
        preferred_provider: Force a specific provider ('groq', 'gemini', 'ollama').

    Returns:
        Generated string response.

    Raises:
        LLMProviderError: If all providers fail or are unavailable.
    """
    providers = [
        ("groq", _call_groq),
        ("gemini", _call_gemini),
        ("ollama", _call_ollama),
    ]

    if preferred_provider:
        providers = [p for p in providers if p[0] == preferred_provider]

    errors: list[str] = []

    for name, caller in providers:
        try:
            return caller(system, user, temperature, max_tokens)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            log_warning(f"LLM provider '{name}' unavailable or throttled ({exc}). Attempting fallback...")

    joined_errors = " | ".join(errors)
    raise LLMProviderError(
        "all",
        f"All LLM providers failed. Details: {joined_errors}. "
        "Please provide a free-tier GROQ_API_KEY or GEMINI_API_KEY in .env, or start local Ollama."
    )
