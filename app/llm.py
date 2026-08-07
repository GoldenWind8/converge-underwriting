"""
Swappable LLM layer. The rest of the app never imports a vendor SDK — it calls
llm.generate(...) and gets back a validated Pydantic object.

Provider is chosen once, from the environment:

    LLM_PROVIDER=gemini|anthropic     explicit choice, or auto-detected:
    GEMINI_API_KEY set                -> gemini      (default for this project)
    ANTHROPIC_API_KEY set             -> anthropic

An LLM is required — main.py and the CLI tools call require() at startup so a
missing key fails immediately with a clear message, not halfway through a request.

Model names can be overridden with LLM_MODEL_MAIN / LLM_MODEL_FAST.
"main" is used for assessment + reflection (quality-critical); "fast" for
profile extraction and case retrieval.

To add a provider: write one _<name>_generate() function and add it to the
dispatch in generate(). Nothing else in the app changes.
"""

from __future__ import annotations

import os
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODELS = {
    "gemini": {"main": "gemini-2.5-pro", "fast": "gemini-2.5-flash"},
    "anthropic": {"main": "claude-opus-4-8", "fast": "claude-haiku-4-5"},
}


def provider() -> str:
    explicit = os.getenv("LLM_PROVIDER")
    if explicit:
        return explicit.strip().lower()
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError(
        "No LLM configured. Set GEMINI_API_KEY (or ANTHROPIC_API_KEY, or "
        "LLM_PROVIDER) — this system does not run without one."
    )


def require() -> str:
    """Fail fast at startup if no provider is configured. Returns the provider name."""
    return provider()


def model_for(tier: str) -> str:
    override = os.getenv(f"LLM_MODEL_{tier.upper()}")
    if override:
        return override
    return DEFAULT_MODELS[provider()][tier]


def generate(system: str, user: str, response_model: Type[T], tier: str = "main") -> T:
    """One structured LLM call: returns a validated instance of response_model."""
    p = provider()
    if p == "gemini":
        return _gemini_generate(system, user, response_model, tier)
    if p == "anthropic":
        return _anthropic_generate(system, user, response_model, tier)
    raise RuntimeError(f"Unknown LLM_PROVIDER '{p}' (expected 'gemini' or 'anthropic').")


def _gemini_generate(system: str, user: str, response_model: Type[T], tier: str) -> T:
    from google import genai

    client = genai.Client()  # reads GEMINI_API_KEY / GOOGLE_API_KEY
    response = client.models.generate_content(
        model=model_for(tier),
        contents=user,
        config={
            "system_instruction": system,
            "response_mime_type": "application/json",
            "response_schema": response_model,
        },
    )
    if response.parsed is not None:
        return response.parsed
    # Fall back to validating the raw JSON text ourselves.
    return response_model.model_validate_json(response.text)


def _anthropic_generate(system: str, user: str, response_model: Type[T], tier: str) -> T:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model_for(tier),
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=response_model,
    )
    if response.parsed_output is None:
        raise ValueError(f"Model did not return schema-valid output (stop_reason={response.stop_reason}).")
    return response.parsed_output
