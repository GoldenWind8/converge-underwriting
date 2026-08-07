"""
Rendering: templates in, HTML out. No logic beyond display.

- index.html     landing page (with an optional one-click sample application)
- review.html    editable draft (the human-review step)
- report.html    final report for an approved case
- cases.html     case-memory listing
- playbook.html  the current playbook
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .guardrails import GuardrailResult
from .models import CaseRecord, RiskAssessmentDraft

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)


def render_index(sample: str = "") -> str:
    return _env.get_template("index.html").render(sample=sample)


def render_review(draft_id: str, draft: RiskAssessmentDraft, result: GuardrailResult,
                  engine: str, generated_at: str) -> str:
    return _env.get_template("review.html").render(
        draft_id=draft_id, draft=draft, result=result, engine=engine, generated_at=generated_at
    )


def render_report(case: CaseRecord, engine: str, generated_at: str,
                  learning_note: Optional[str] = None) -> str:
    return _env.get_template("report.html").render(
        case=case, engine=engine, generated_at=generated_at, learning_note=learning_note
    )


def render_cases(cases: List[CaseRecord]) -> str:
    return _env.get_template("cases.html").render(cases=cases)


def render_playbook(playbook: str) -> str:
    return _env.get_template("playbook.html").render(playbook=playbook)
