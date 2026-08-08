"""
Swappable LLM layer. The rest of the app never imports a vendor SDK — it calls
llm.generate(...) and gets back a validated Pydantic object.

Provider is chosen once, from the environment:

    LLM_PROVIDER=gemini|anthropic|claude-cli   explicit choice, or auto-detected:
    GEMINI_API_KEY set                         -> gemini      (default for this project)
    ANTHROPIC_API_KEY set                      -> anthropic
    `claude` CLI on PATH                       -> claude-cli  (keyless local route)

The claude-cli route runs on whatever Claude Code login the machine already
has — no service credential. It exists so prompts can be iterated on locally
before any key is authorised (docs/CONSOLIDATION_PLAN.md §9). It is not a
production route.

An LLM is required — main.py and the CLI tools call require() at startup so a
missing provider fails immediately with a clear message, not halfway through a
request.

Model names can be overridden with LLM_MODEL_MAIN / LLM_MODEL_FAST.
"main" is used for needs determination, assessment + reflection
(quality-critical); "fast" for profile extraction and case retrieval.

Every call appends a UsageRecord to usage_log (tokens always when the provider
reports them; cost when it reports that too) — iteration you cannot measure is
iteration you cannot budget.

To add a provider: write one _<name>_generate() function and add it to the
dispatch in generate(). Nothing else in the app changes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODELS = {
    "gemini": {"main": "gemini-2.5-pro", "fast": "gemini-2.5-flash"},
    "anthropic": {"main": "claude-opus-4-8", "fast": "claude-haiku-4-5"},
    "claude-cli": {"main": "opus", "fast": "haiku"},
}

CLI_TIMEOUT_S = int(os.getenv("UW_CLI_TIMEOUT_S", "240"))


@dataclass
class UsageRecord:
    provider: str
    tier: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None


usage_log: List[UsageRecord] = []


def reset_usage() -> None:
    usage_log.clear()


def usage_summary() -> dict:
    """Totals over usage_log: calls, tokens where reported, cost where reported."""
    return {
        "calls": len(usage_log),
        "input_tokens": sum(u.input_tokens or 0 for u in usage_log),
        "output_tokens": sum(u.output_tokens or 0 for u in usage_log),
        "cost_usd": sum(u.cost_usd or 0.0 for u in usage_log),
    }


def provider() -> str:
    explicit = os.getenv("LLM_PROVIDER")
    if explicit:
        return explicit.strip().lower()
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if shutil.which("claude"):
        return "claude-cli"
    raise RuntimeError(
        "No LLM configured. Set GEMINI_API_KEY (or ANTHROPIC_API_KEY, or "
        "LLM_PROVIDER, or install the claude CLI for the keyless local route) "
        "— this system does not run without one."
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
    if p == "claude-cli":
        return _claude_cli_generate(system, user, response_model, tier)
    raise RuntimeError(f"Unknown LLM_PROVIDER '{p}' (expected 'gemini', 'anthropic' or 'claude-cli').")


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
    meta = getattr(response, "usage_metadata", None)
    usage_log.append(UsageRecord(
        provider="gemini", tier=tier, model=model_for(tier),
        input_tokens=getattr(meta, "prompt_token_count", None),
        output_tokens=getattr(meta, "candidates_token_count", None),
    ))
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
    usage = getattr(response, "usage", None)
    usage_log.append(UsageRecord(
        provider="anthropic", tier=tier, model=model_for(tier),
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    ))
    if response.parsed_output is None:
        raise ValueError(f"Model did not return schema-valid output (stop_reason={response.stop_reason}).")
    return response.parsed_output


def _claude_cli_generate(system: str, user: str, response_model: Type[T], tier: str) -> T:
    """Local-evaluation route: the Claude Code CLI, using whatever login the
    machine already has. Transport only — schema-validated like every route."""
    argv = [
        "claude",
        "--print",
        "--output-format", "json",
        "--model", model_for(tier),
        # Replace, never append: Claude Code's default agent prompt is large and
        # irrelevant here.
        "--system-prompt", system,
        "--exclude-dynamic-system-prompt-sections",
        # One text-in / JSON-out call. The model gets no tools at all.
        "--tools", "",
        # Best-effort schema enforcement; output is still validated below.
        "--json-schema", json.dumps(response_model.model_json_schema()),
        # A one-shot call should not accumulate session history on the machine.
        "--no-session-persistence",
    ]
    try:
        # The submission is multi-line free text, so it goes on stdin, not argv.
        completed = subprocess.run(
            argv, input=user, capture_output=True, text=True, timeout=CLI_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("could not run the claude CLI: binary not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"the claude CLI did not respond within {CLI_TIMEOUT_S}s. Retry, or set "
            "an API key to use an SDK route."
        ) from exc

    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = (completed.stderr or completed.stdout).strip()[:500]
        raise RuntimeError(
            f"the claude CLI returned output that is not a JSON envelope "
            f"(exit {completed.returncode}): {detail}"
        ) from exc

    if completed.returncode != 0 or envelope.get("is_error"):
        detail = str(envelope.get("result") or completed.stderr).strip()[:500]
        raise RuntimeError(f"the claude CLI reported a failure (exit {completed.returncode}): {detail}")

    result = envelope.get("result")
    if not isinstance(result, str):
        raise RuntimeError("the claude CLI envelope had no text result")

    usage = envelope.get("usage") or {}
    usage_log.append(UsageRecord(
        provider="claude-cli", tier=tier, model=model_for(tier),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cost_usd=envelope.get("total_cost_usd"),
    ))
    # The CLI cannot guarantee bare JSON the way a server-side schema does, so
    # pull the object out defensively. Validation is unchanged.
    return response_model.model_validate_json(_extract_json_object(result))


def _extract_json_object(text: str) -> str:
    """Pull the first complete JSON object out of model text, tolerating code
    fences and surrounding prose. Returns the input unchanged when it finds
    nothing, so the caller's validator produces the error rather than this."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
        stripped = stripped.strip()
    start = stripped.find("{")
    if start == -1:
        return stripped
    balanced = _take_balanced_object(stripped[start:])
    return balanced if balanced is not None else stripped


def _take_balanced_object(text: str) -> Optional[str]:
    """Scan a leading `{...}` object, respecting strings and escapes."""
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if in_string:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[: i + 1]
    return None
