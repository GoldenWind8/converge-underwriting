"""
Rendering: templates in, HTML out. No logic beyond display.

- index.html     landing page (with an optional one-click sample application)
- review.html    editable draft (the human-review step)
- report.html    final report for an approved case
- cases.html     case-memory listing
- playbook.html  the current playbook
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .guardrails import GuardrailResult
from .memory import LearningProposal
from .models import CaseRecord, RiskAssessmentDraft

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)


def render_index(sample: str = "", case_count: int = 0, rule_count: int = 0) -> str:
    return _env.get_template("index.html").render(
        sample=sample, case_count=case_count, rule_count=rule_count
    )


def render_review(draft_id: str, draft: RiskAssessmentDraft, result: GuardrailResult,
                  engine: str, generated_at: str, raw_text: str = "") -> str:
    return _env.get_template("review.html").render(
        draft_id=draft_id, draft=draft, result=result, engine=engine,
        generated_at=generated_at, raw_text=raw_text,
    )


def render_report(case: CaseRecord, engine: str, generated_at: str,
                  learning_note: Optional[str] = None,
                  learning_proposal: Optional[LearningProposal] = None) -> str:
    return _env.get_template("report.html").render(
        case=case, engine=engine, generated_at=generated_at,
        learning_note=learning_note, learning_proposal=learning_proposal,
    )


def render_cases(cases: List[CaseRecord]) -> str:
    return _env.get_template("cases.html").render(cases=cases)


def render_playbook(playbook: str) -> str:
    rules = []
    matches = list(re.finditer(r"^##\s+(PB-\d+)\s*[·\-–—:]?\s*(.*)$", playbook, re.MULTILINE | re.IGNORECASE))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(playbook)
        rules.append({
            "id": match.group(1).upper(),
            "title": match.group(2).strip(),
            "body": playbook[match.end():end].strip(),
        })
    return _env.get_template("playbook.html").render(playbook=playbook, rules=rules)


def render_error(title: str, message: str, retry_href: str = "/") -> str:
    return _env.get_template("error.html").render(
        title=title, message=message, retry_href=retry_href
    )
