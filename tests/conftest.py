"""Shared fixtures: an isolated data dir per test, and a fake LLM.

The fake LLM replaces llm.generate with a lookup keyed on the response model's
class name — tests register the object (or a function) each call should return.
This keeps tests offline and deterministic without any fallback logic in the app.
"""

import pytest

from app import llm


class FakeLLM:
    def __init__(self):
        self.responses = {}
        self.calls = []  # (model_name, tier, system, user)

    def register(self, model_cls, value):
        """value: a model instance, or fn(system, user) -> instance."""
        self.responses[model_cls.__name__] = value

    def generate(self, system, user, response_model, tier="main"):
        self.calls.append((response_model.__name__, tier, system, user))
        value = self.responses[response_model.__name__]
        return value(system, user) if callable(value) else value


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("UW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UW_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "generate", fake.generate)
    monkeypatch.setattr(llm, "provider", lambda: "fake")
    monkeypatch.setattr(llm, "require", lambda: "fake")
    return fake
