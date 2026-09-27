"""The provider layer decides whether the application can reach a model at all,
so when it breaks it breaks at startup, for everyone. Nothing else in the suite
exercises it: `conftest.fake_llm` stubs `llm.provider` out, and these tests
deliberately never request that fixture — they drive the real function.

Two things are under test. Which provider a given environment resolves to
(including the precedence between the routes, which is where the interesting
mistakes live), and — for the keyless `claude-cli` route — whether the transport
still hands back a schema-validated object when the CLI replies with something
messy. Everything runs offline: no key is ever real, and the only `claude`
binary involved is a stub file on a temporary PATH.
"""

import json
import subprocess

import pytest
from pydantic import BaseModel

from app import llm

ENV_KEYS = (
    "LLM_PROVIDER",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "LLM_MODEL_MAIN",
    "LLM_MODEL_FAST",
)


class Answer(BaseModel):
    label: str
    score: int


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    """Nothing configured: no keys, and a PATH with no `claude` on it.

    PATH is redirected at an empty directory rather than patching `shutil.which`,
    so the auto-detection under test is the real one.
    """
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    path_dir = tmp_path / "bin"
    path_dir.mkdir()
    monkeypatch.setenv("PATH", str(path_dir))
    monkeypatch.setattr(llm, "usage_log", [])
    return monkeypatch


@pytest.fixture
def cli_on_path(clean_env, tmp_path):
    """Install an executable stub named `claude` on the (empty) PATH."""
    binary = tmp_path / "bin" / "claude"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    return binary


# --- provider selection -----------------------------------------------------


def test_precedence_ladder_from_nothing_configured_up_to_an_explicit_choice(cli_on_path, clean_env):
    """Walk the whole ladder in one pass, because precedence is the contract.

    Each rung is added on top of the one below it, so every assertion after the
    first is really asking "does the higher-priority source still win?".
    """
    env = clean_env

    # Rung 1: a `claude` binary alone is enough — the keyless local route.
    assert llm.provider() == "claude-cli"

    # Rung 2: any key outranks the CLI. Adding the keyless route must never
    # change behaviour for someone who already holds a credential.
    env.setenv("ANTHROPIC_API_KEY", "sk-ant-not-real")
    assert llm.provider() == "anthropic"

    # Rung 3: gemini is this project's default, so it outranks anthropic.
    env.setenv("GEMINI_API_KEY", "g-not-real")
    assert llm.provider() == "gemini"

    # GOOGLE_API_KEY is the same rung as GEMINI_API_KEY, not a lower one.
    env.delenv("GEMINI_API_KEY")
    env.setenv("GOOGLE_API_KEY", "g-not-real")
    assert llm.provider() == "gemini"

    # Rung 4: an explicit choice beats every key, including a route whose own
    # credential is absent.
    env.setenv("LLM_PROVIDER", "anthropic")
    assert llm.provider() == "anthropic"
    env.setenv("LLM_PROVIDER", "claude-cli")
    assert llm.provider() == "claude-cli"

    # An explicit choice is normalised, so a stray case or space is not a new
    # provider name that fails later inside generate().
    env.setenv("LLM_PROVIDER", "  Anthropic \n")
    assert llm.provider() == "anthropic"


@pytest.mark.parametrize(
    "env, expected",
    [
        # An unset variable and an empty one must behave identically, or a
        # blanked-out `.env` entry silently pins the wrong provider.
        ({"LLM_PROVIDER": "", "ANTHROPIC_API_KEY": "sk-ant-not-real"}, "anthropic"),
        ({"GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant-not-real"}, "anthropic"),
        ({"ANTHROPIC_API_KEY": ""}, "claude-cli"),
        ({"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, "claude-cli"),
        # An unrecognised explicit value is still honoured here; it is the
        # dispatch in generate() that rejects it, with a message naming it.
        ({"LLM_PROVIDER": "vertex"}, "vertex"),
    ],
    ids=["blank-provider", "blank-gemini-key", "blank-anthropic-key", "both-google-keys-blank", "unknown-name"],
)
def test_blank_values_do_not_count_as_configured(cli_on_path, clean_env, env, expected):
    for key, value in env.items():
        clean_env.setenv(key, value)
    assert llm.provider() == expected


def test_nothing_configured_fails_immediately_and_names_every_route(clean_env):
    """The failure has to arrive at startup and has to be actionable — a run
    that dies halfway through has already cost the user their submission."""
    with pytest.raises(RuntimeError) as excinfo:
        llm.require()
    message = str(excinfo.value)

    assert "No LLM configured" in message
    for route in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "claude"):
        assert route in message, f"the fix-it message should mention {route}"

    # Same failure through every public entry point, not just require().
    with pytest.raises(RuntimeError, match="No LLM configured"):
        llm.provider()
    with pytest.raises(RuntimeError, match="No LLM configured"):
        llm.model_for("main")
    with pytest.raises(RuntimeError, match="No LLM configured"):
        llm.generate("sys", "user", Answer)


def test_require_returns_the_resolved_provider_once_configured(cli_on_path, clean_env):
    assert llm.require() == "claude-cli"
    clean_env.setenv("GEMINI_API_KEY", "g-not-real")
    assert llm.require() == "gemini"


# --- model mapping ----------------------------------------------------------


@pytest.mark.parametrize(
    "provider_name, main, fast",
    [
        ("gemini", "gemini-2.5-pro", "gemini-2.5-flash"),
        ("anthropic", "claude-opus-4-8", "claude-haiku-4-5"),
        # The CLI takes Claude Code's short aliases, not full model ids.
        ("claude-cli", "opus", "haiku"),
    ],
)
def test_each_provider_maps_its_own_main_and_fast_models(clean_env, provider_name, main, fast):
    clean_env.setenv("LLM_PROVIDER", provider_name)
    assert llm.model_for("main") == main
    assert llm.model_for("fast") == fast
    assert main != fast, "the two tiers must be distinct or the fast tier is not a saving"

    # An override replaces exactly one tier and leaves the other on its default.
    clean_env.setenv("LLM_MODEL_MAIN", "an-override")
    assert llm.model_for("main") == "an-override"
    assert llm.model_for("fast") == fast


def test_an_unknown_provider_is_rejected_by_name(clean_env):
    clean_env.setenv("LLM_PROVIDER", "vertex")
    with pytest.raises(KeyError):
        llm.model_for("main")
    with pytest.raises(RuntimeError, match="Unknown LLM_PROVIDER 'vertex'"):
        llm.generate("sys", "user", Answer)


# --- the keyless route, end to end ------------------------------------------


def _fake_cli(result, *, returncode=0, is_error=False, usage=None, cost=None, stdout=None):
    """Stand in for the `claude` subprocess and record how it was invoked."""
    envelope = json.dumps({
        "is_error": is_error,
        "result": result,
        "usage": usage or {},
        "total_cost_usd": cost,
    })
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, returncode, stdout=envelope if stdout is None else stdout, stderr="",
        )

    run.calls = calls
    return run


CLEAN = '{"label": "high", "score": 7}'
FENCED = 'Here is the assessment:\n\n```json\n{"label": "high", "score": 7}\n```\n'
PROSE = 'Based on the document my answer is {"label": "high", "score": 7} - hope that helps.'
NESTED = '{"label": "high", "score": 7, "note": "the brace } is inside a string"}'


def test_keyless_route_runs_a_submission_end_to_end(cli_on_path, clean_env):
    """One realistic pass: nothing but a CLI on PATH, through selection, model
    resolution, invocation and validation, out to a usage record."""
    run = _fake_cli(CLEAN, usage={"input_tokens": 1200, "output_tokens": 90}, cost=0.031)
    clean_env.setattr(subprocess, "run", run)

    result = llm.generate("You assess risk.", "Some long\nmulti-line submission.", Answer, tier="fast")

    assert isinstance(result, Answer)
    assert (result.label, result.score) == ("high", 7)

    command, kwargs = run.calls[0]
    assert command[0] == "claude"
    # The submission is multi-line free text: stdin, never argv.
    assert kwargs["input"] == "Some long\nmulti-line submission."
    assert "Some long" not in " ".join(command)
    assert kwargs["timeout"] == llm.CLI_TIMEOUT_S
    # The requested tier picks the model, and the model is the CLI's alias.
    assert command[command.index("--model") + 1] == "haiku"
    # The app's prompt replaces Claude Code's agent prompt rather than appending
    # to it, and the model is granted no tools at all.
    assert command[command.index("--system-prompt") + 1] == "You assess risk."
    assert "--append-system-prompt" not in command
    assert command[command.index("--tools") + 1] == ""
    assert "--no-session-persistence" in command
    # The schema travels as a flag, not smuggled into the prompt.
    schema = json.loads(command[command.index("--json-schema") + 1])
    assert set(schema["properties"]) == {"label", "score"}

    assert llm.usage_summary() == {
        "calls": 1, "input_tokens": 1200, "output_tokens": 90, "cost_usd": 0.031,
    }
    assert llm.usage_log[0].provider == "claude-cli"
    assert llm.usage_log[0].tier == "fast"


@pytest.mark.parametrize(
    "raw", [CLEAN, FENCED, PROSE, NESTED], ids=["clean", "fenced", "prose", "brace-in-string"],
)
def test_a_messy_cli_reply_still_yields_a_validated_object(cli_on_path, clean_env, raw):
    """The CLI cannot guarantee bare JSON the way a server-side schema can, so
    the extraction has to survive fences, surrounding prose, and braces that
    only look like structure."""
    clean_env.setattr(subprocess, "run", _fake_cli(raw))
    assert llm.generate("sys", "user", Answer) == Answer(label="high", score=7)


@pytest.mark.parametrize(
    "raw, expected_in_message",
    [
        ("I would rather explain in words.", "I would rather explain in words."),
        ('{"label": "high"}', "score"),
        ('{"label": "high", "score": "seven"}', "score"),
    ],
    ids=["no-json", "missing-field", "wrong-type"],
)
def test_output_that_will_not_validate_raises_rather_than_coercing(
    cli_on_path, clean_env, raw, expected_in_message
):
    """Everything downstream assumes a real object, never a half-filled one."""
    clean_env.setattr(subprocess, "run", _fake_cli(raw))
    with pytest.raises(ValueError) as excinfo:
        llm.generate("sys", "user", Answer)
    assert expected_in_message in str(excinfo.value)


def test_cli_failures_surface_with_the_reason_attached(cli_on_path, clean_env):
    """Each failure mode has to be distinguishable from the others, because the
    fix differs: retry, log in again, or raise the timeout."""
    clean_env.setattr(subprocess, "run", _fake_cli("some detail", returncode=1))
    with pytest.raises(RuntimeError, match="exit 1"):
        llm.generate("sys", "user", Answer)

    clean_env.setattr(subprocess, "run", _fake_cli("rate limited", is_error=True))
    with pytest.raises(RuntimeError, match="rate limited"):
        llm.generate("sys", "user", Answer)

    clean_env.setattr(subprocess, "run", _fake_cli(None, stdout="Usage: claude [options]"))
    with pytest.raises(RuntimeError, match="not a JSON envelope"):
        llm.generate("sys", "user", Answer)

    clean_env.setattr(subprocess, "run", _fake_cli(12345))
    with pytest.raises(RuntimeError, match="no text result"):
        llm.generate("sys", "user", Answer)

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    clean_env.setattr(subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="did not respond within"):
        llm.generate("sys", "user", Answer)

    def missing(command, **kwargs):
        raise FileNotFoundError(command[0])

    clean_env.setattr(subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="binary not found on PATH"):
        llm.generate("sys", "user", Answer)

    # A failed call must not leave a usage record behind to skew the totals.
    assert llm.usage_summary()["calls"] == 0
