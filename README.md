<p align="center">
  <img src="app/static/converge-underwriting-logo.svg" alt="Converge Underwriting" width="720" />
</p>

# Converge Underwriting — POC

An enterprise underwriting-intelligence concept from [Converge AI](https://convergeai.co.za/),
combining governed AI agents, workflow automation, and institutional knowledge.

Takes a raw commercial-insurance application (form, email, broker notes), works out
which of the 18 cover sections the business actually needs, drafts a per-section
risk assessment, prices each required section deterministically from broker base
rates, and **learns from every human review**: corrections update a plain markdown
playbook and approved cases become retrievable precedents, so the very next
assessment is better.

```
raw input ─▶ PROFILE ─▶ NEEDS DETERMINATION ─▶ GATE 1: confirm sections
             + SUMS INSURED   (18 sections)          + sums insured
             ┌───────────────────────────────────────┘
             ▼
        ASSESS (one call per required section) ─▶ GUARDRAILS ─▶ GATE 2: human review
             ▲  ▲                                 (deterministic)      │
             │  └── playbook.md (section-tagged rules)                 ▼
             │                        PRICING ENGINE ◀── approved case
             │      (deterministic: sum insured × rate × loading)
             │                           │
             │                           ▼ GATE 3: confirm/override loadings
             └── similar past cases ◀── case memory ── report / PDF
                                             │
                                             └─▶ REFLECT ─▶ GATE 4: accept/edit/skip ─▶ playbook.md
```

- **Needs determination** — every one of the 18 cover sections (transcribed from the
  broker needs analysis PDF) is classified required / not-applicable, with a one-line
  reason and a Motor sub-type where Motor is in play. Sums insured stated in the
  submission are extracted and pre-filled per section. The underwriter confirms the
  table (gate 1); what it says *required* is what gets assessed and priced, and only
  a confirmed sum insured is ever priced. Not-applicable sections disappear from
  everything downstream.
- **Assess** — one focused model call per confirmed section, run concurrently so a
  submission takes about as long as its slowest section. The LLM proposes its own
  risk factors, informed by the section-tagged playbook rules and the comparable
  approved cases for that section. Every finding must quote verbatim evidence.
- **Guardrails** — deterministic: hallucinated or insubstantial evidence is dropped,
  unverifiable citations are removed, bands (per case and per section) are derived
  from the severity profile, and severe / novel / low-confidence findings are
  referred to a human. The LLM deliberately emits **no numeric score and no price**
  — severity is a standardised categorical scale (low / medium / high / severe).
  The exact rules are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#what-guards-what).
- **Human review** — a split-screen decision workspace (gate 2) links each finding to
  its source evidence, recomputes the band live, and captures the reviewer's own
  "why" note verbatim on every edit. Only approved cases ever enter memory.
- **Price** — a deterministic engine, no LLM (gate 3): per required section,
  `sum insured × base rate × (1 + band loading)`, quoting both the base and the
  adjusted premium with the findings that set the band as justification. Base rates
  (flat per section, placeholder values until the broker's rate sheet lands) and the
  band→loading table are git-tracked JSON in `config/`, editable on the **Rates**
  page. The underwriter can override a loading per section; overrides are disclosed
  against the table value on screen and on the PDF. No confirmed sum insured means
  "not priced" — never a guess.
- **Reflect** — after sign-off, corrections (with their why-notes) become an editable,
  section-tagged playbook proposal. The underwriter must accept it (gate 3) before it
  becomes active; every previous version is retained in `data/playbook_history/`.

How the pieces link together (with diagrams): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
Design rationale and the decisions behind it: **[docs/SOLUTION_DESIGN.md](docs/SOLUTION_DESIGN.md)**.
Visual identity: **[docs/BRAND.md](docs/BRAND.md)**.

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

Paste `sample_data/sample_application.md` (or click **Load guided sample**), or upload a
`.txt` / `.md` / `.csv` (250 KB max) — a completed copy of the broker intake sheet in
`sample_data/` works well. Confirm the needs table, review the draft, change a severity
and say why, approve the case, confirm the premium
table (override a loading and see it disclosed), and accept the proposed playbook lesson.
Assess a similar client and watch the next finding cite both the precedent case and the
newly governed rule.

Once a case is approved, **Save PDF copy** on the decision page (or `GET /cases/{id}/pdf`)
downloads a client-facing report: `app/templates/case_pdf.html` rendered and converted with
xhtml2pdf (pure Python, no browser needed). Internal codes — factor slugs, playbook rule
ids, precedent ids, confidence, reviewer edits — are left out of it.
`sample_data/Converge-Underwriting-C-0002-XYZ-Shoes.pdf` is an example of the output.

**Reset** on the case-memory page (`POST /demo/reset`) empties case memory and the
playbook, keeping the archived playbook versions.

## Choosing the AI

The vendor lives in one file, `app/llm.py`, picked from the environment:

| Environment | Engine |
|---|---|
| `GEMINI_API_KEY` set | Google Gemini (`gemini-2.5-pro` / `-flash`) — the default for this project |
| `ANTHROPIC_API_KEY` set | Claude (`claude-opus-4-8` / `claude-haiku-4-5`) |
| neither, `claude` CLI on PATH | Claude Code CLI on the machine's existing login — keyless, for local prompt iteration only |

`LLM_PROVIDER`, `LLM_MODEL_MAIN`, `LLM_MODEL_FAST` override the defaults; `UW_CLI_TIMEOUT_S`
(default 240) bounds a CLI call. "Main" handles needs determination, assessment and
reflection; "fast" handles profile extraction, precedent retrieval and chat ingestion.
Every call's tokens (and cost, where the provider reports it) are captured and
shown on the review page. Adding a provider is one `_<name>_generate()` function in
`app/llm.py`.

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
  sums.py          sum-insured extraction (transcribes stated figures; broker confirms at gate 1)
  assess.py        per-section assessment (prompt = section scope + rules + precedents + document)
  guardrails.py    deterministic evidence check, severity bands (case + per section), referrals
  pricing.py       deterministic pricing engine (sum insured × rate × band loading) — no LLM
  memory.py        SQLite case store, retrieval, section-tagged playbook + reflection
  main.py          FastAPI routes;  report.py + templates/  HTML rendering
  pdf.py           client-facing PDF of an approved case (templates/case_pdf.html + xhtml2pdf)
  ingest_chats.py  seed memory (provisional) from historical chats;  evaluate.py  eval harness
config/            rates.json (base rate per section) + loadings.json (band → loading %) —
                   git-tracked, editable on /rates, placeholders until the broker's rate sheet
data/              cases.db, playbook.md, playbook_history/  (git-ignored; safe to delete)
sample_data/       example application, blank broker intake sheet (PDF + text), example
                   PDF output, synthetic historical chats
tests/             sections, needs, guardrails, memory, flow, review, UI, PDF, learning loop
                   (LLM faked — offline)
Needs Analysis.pdf the broker needs analysis that sections.py transcribes
```
