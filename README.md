<p align="center">
  <img src="app/static/converge-underwriting-logo.svg" alt="Converge Underwriting" width="720" />
</p>

# Converge Underwriting — POC

An enterprise underwriting-intelligence concept from [Converge AI](https://convergeai.co.za/),
combining governed AI agents, workflow automation, and institutional knowledge.

Takes a raw commercial-insurance application (form, email, broker notes), works out
which of the 18 cover sections the business actually needs, drafts a per-section
risk assessment, and **learns from every human review**: corrections update a plain
markdown playbook and approved cases become retrievable precedents, so the very next
assessment is better.

```
raw input ─▶ PROFILE ─▶ NEEDS DETERMINATION ─▶ GATE 1: confirm sections
                              (18 sections)          │
             ┌───────────────────────────────────────┘
             ▼
        ASSESS (one call per required section) ─▶ GUARDRAILS ─▶ DRIVER ROLL-UP
             ▲  ▲                                 (deterministic)      │
             │  └── playbook.md (section-tagged rules)                 ▼
             └───── similar past cases ◀── case memory ◀── GATE 2: human review
                                               │
                                               └─▶ REFLECT ─▶ GATE 3: accept/edit/skip ─▶ playbook.md
```

- **Needs determination** — every one of the 18 cover sections (transcribed from the
  broker needs analysis PDF) is classified required / consider / not-applicable, with
  a one-line reason and a Motor sub-type where Motor is in play. The underwriter
  confirms the table (gate 1); what it says *required* is what gets assessed.
- **Assess** — one focused model call per confirmed section, run concurrently so a
  submission takes about as long as its slowest section. The LLM proposes its own
  risk factors, informed by the section-tagged playbook rules and the comparable
  approved cases for that section. Every finding must quote verbatim evidence.
- **Guardrails** — deterministic: hallucinated or insubstantial evidence is dropped,
  unverifiable citations are removed, the referral band is derived from the severity
  profile, and severe / novel / low-confidence findings are referred to a human.
  There is deliberately **no numeric score and no pricing anywhere** — severity is a
  standardised categorical scale (low / medium / high / severe).
- **Human review** — a split-screen decision workspace (gate 2) links each finding to
  its source evidence, recomputes the band live, and captures the reviewer's own
  "why" note verbatim on every edit. Only approved cases ever enter memory.
- **Reflect** — after sign-off, corrections (with their why-notes) become an editable,
  section-tagged playbook proposal. The underwriter must accept it (gate 3) before it
  becomes active; every previous version is retained in `data/playbook_history/`.

How the pieces link together (with diagrams): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
Full design rationale: **[docs/SOLUTION_DESIGN.md](docs/SOLUTION_DESIGN.md)**.
The consolidation this build implements: **[docs/CONSOLIDATION_PLAN.md](docs/CONSOLIDATION_PLAN.md)**.

## Run it

An LLM is **required** — without one the app exits at startup with a clear error.
A key is not: with the `claude` CLI installed and logged in, the keyless local
route is used automatically.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=...         # or ANTHROPIC_API_KEY, or neither (claude CLI route)

python -m app.ingest_chats        # optional: seed memory from sample historical chats
                                  # (ingested cases are provisional until confirmed on /cases)
uvicorn app.main:app --reload     # open http://127.0.0.1:8000
```

Paste `sample_data/sample_application.md` (or click **Load guided sample**), confirm
the needs table, review the draft, change a severity and say why, approve the case,
and accept the proposed playbook lesson. Assess a similar client and watch the next
finding cite both the precedent case and the newly governed rule.

## Choosing the AI

The vendor lives in one file, `app/llm.py`, picked from the environment:

| Environment | Engine |
|---|---|
| `GEMINI_API_KEY` set | Google Gemini (`gemini-2.5-pro` / `-flash`) — the default for this project |
| `ANTHROPIC_API_KEY` set | Claude (`claude-opus-4-8` / `claude-haiku-4-5`) |
| neither, `claude` CLI on PATH | Claude Code CLI on the machine's existing login — keyless, for local prompt iteration only |

`LLM_PROVIDER`, `LLM_MODEL_MAIN`, `LLM_MODEL_FAST` override the defaults.
Every call's tokens (and cost, where the provider reports it) are captured and
shown on the review page.

## Test & evaluate

```bash
pytest -q               # offline — tests fake the LLM (tests/conftest.py)
python -m app.evaluate  # memory-on vs memory-off comparison (needs an LLM + stored cases)
```

## Layout

```
app/
  llm.py           swappable LLM layer (gemini | anthropic | claude-cli) — the only vendor code
  sections.py      the 18 cover sections (PDF-verified), Motor sub-types
  models.py        RiskFinding, SectionNeed, CaseRecord, … (Pydantic)
  needs.py         needs determination (which sections apply) — human gate 1 feeds on this
  assess.py        per-section assessment (prompt = section scope + rules + precedents + document)
  guardrails.py    deterministic evidence check, severity band, referrals
  memory.py        SQLite case store, retrieval, section-tagged playbook + reflection
  main.py          FastAPI routes;  report.py + templates/  rendering
  ingest_chats.py  seed memory (provisional) from historical chats;  evaluate.py  eval harness
data/              cases.db, playbook.md, playbook_history/  (safe to delete)
sample_data/       example application + synthetic historical chats
tests/             sections, needs, guardrails, memory, learning loop (LLM faked — offline)
```
