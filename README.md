# Self-Learning Underwriting — POC

Takes a raw commercial-insurance application (form, email, broker notes), drafts a
risk assessment, and **learns from every human review**: corrections update a plain
markdown playbook and approved cases become retrievable precedents, so the very next
assessment is better.

```
raw input ─▶ ASSESS ─▶ GUARDRAILS ─▶ HUMAN REVIEW ─▶ REPORT
             ▲  ▲       (deterministic)     │
             │  └── playbook.md             ├─▶ case memory (SQLite)
             └───── similar past cases ◀────┘        │
                                                     └─▶ REFLECT → playbook.md
```

- **Assess** — the LLM proposes its own risk factors, informed by the playbook and
  the k most comparable approved cases. Every finding must quote verbatim evidence.
- **Guardrails** — deterministic: hallucinated evidence is dropped, points are capped
  per severity, bands are fixed, novel/low-confidence findings are referred to a human.
- **Human review** — the report is an editable draft; **Approve** is the learning signal.
  Only approved cases ever enter memory.
- **Reflect** — after each sign-off, corrections are distilled into `data/playbook.md`
  (human-readable, versioned in `data/playbook_history/`).

How the pieces link together (with diagrams): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
Full design rationale: **[docs/SOLUTION_DESIGN.md](docs/SOLUTION_DESIGN.md)**.

## Run it

An LLM key is **required** — without one the app exits at startup with a clear error.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=...         # or ANTHROPIC_API_KEY

python -m app.ingest_chats        # optional: seed memory from sample historical chats
uvicorn app.main:app --reload     # open http://127.0.0.1:8000
```

Paste `sample_data/sample_application.md` (any free-form text works), review the
draft, change a severity, approve — then assess a similar client and watch the
finding cite the precedent case and the new playbook rule.

## Choosing the AI

The vendor lives in one file, `app/llm.py`, picked from the environment:

| Environment | Engine |
|---|---|
| `GEMINI_API_KEY` set | Google Gemini (`gemini-2.5-pro` / `-flash`) — the default for this project |
| `ANTHROPIC_API_KEY` set | Claude (`claude-opus-4-8` / `claude-haiku-4-5`) |

`LLM_PROVIDER`, `LLM_MODEL_MAIN`, `LLM_MODEL_FAST` override the defaults.

## Test & evaluate

```bash
pytest -q               # offline — tests fake the LLM (tests/conftest.py)
python -m app.evaluate  # memory-on vs memory-off comparison (needs a key + stored cases)
```

## Layout

```
app/
  llm.py           swappable LLM layer (gemini | anthropic) — the only vendor code
  models.py        RiskFinding, CaseRecord, … (Pydantic)
  assess.py        the assessment call (prompt = playbook + precedents + document)
  guardrails.py    deterministic evidence check, caps, bands, referrals
  memory.py        SQLite case store, retrieval, playbook + reflection
  main.py          FastAPI routes;  report.py + templates/  rendering
  ingest_chats.py  seed memory from historical chats;  evaluate.py  eval harness
data/              cases.db, playbook.md, playbook_history/  (safe to delete)
sample_data/       example application + synthetic historical chats
tests/             guardrails, memory, learning loop (LLM faked — runs offline)
```
