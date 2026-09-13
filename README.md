<p align="center">
  <img src="app/static/converge-underwriting-logo.svg" alt="Converge Underwriting" width="720" />
</p>

# Converge Underwriting — POC

An enterprise underwriting-intelligence concept from [Converge AI](https://convergeai.co.za/),
combining governed AI agents, workflow automation, and institutional knowledge.

Takes a raw commercial-insurance application (form, email, broker notes), works out
which of the 18 cover sections the business actually needs, drafts a per-section
risk assessment, prices each required section deterministically from broker base
rates, and **learns from every approved case**: the case — with the underwriter's
corrections and why-notes — becomes a retrievable precedent for the next assessment
of the same sections, so the very next assessment is better.

```
raw input ─▶ PROFILE ─▶ NEEDS DETERMINATION ─▶ GATE 1: confirm sections
             + SUMS INSURED   (18 sections)          + a sum insured for each
             ┌───────────────────────────────────────┘
             ▼
        ASSESS (one call per required section) ─▶ GUARDRAILS ─▶ PRICING ENGINE
             ▲                                   (deterministic)  (deterministic)
             │                                                          │
             │                          GATE 2: rate each finding, confirm loadings,
             │                                  "checked by", approve
             │                                     ▲ │           │
             │               review drill-down ────┘ │           ▼
             │            (evidence, add / remove)   │      report / PDF
             └── similar approved cases ◀── case memory ◀── add to memory ✓
                 (+ the reviewer's corrections)
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
  risk factors, informed by the comparable approved cases for that section — each
  carrying the reviewer's corrections and why-notes. Every finding must quote
  verbatim evidence.
- **Guardrails** — deterministic: hallucinated or insubstantial evidence is dropped,
  unverifiable citations are removed, bands (per case and per section) are derived
  from the severity profile, and severe / novel / low-confidence findings are
  referred to a human. The LLM deliberately emits **no numeric score and no price**
  — severity is a standardised categorical scale (low / medium / high / severe).
  The exact rules are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#what-guards-what).
- **Rate & price** — the approval gate (gate 2), one page. Per required section the
  deterministic premium row — `sum insured × base rate × (1 + band loading)`, no LLM —
  with the findings that set the band listed under it as identifier · rating ·
  description. Change a rating and the section re-bands and re-prices instantly;
  override a loading and it is disclosed against the table value on screen and on
  the PDF. Base rates (flat per section, placeholder values until the broker's rate
  sheet lands) and the band→loading table are git-tracked JSON in `config/`, editable
  on the **Rates** page. **Checked by** is required; **Add to case memory** decides
  whether the case becomes a precedent. Only approved cases ever enter memory.
- **Review drill-down** — from the price page, a split-screen workspace links each
  finding to its source evidence, lets the reviewer remove or add findings (evidence
  required), and captures their own "why" note verbatim on every edit. Save & go back
  returns to the price page; nothing is stored until approval.
- **Case memory** — every approved case is listed with who checked it; a case can be
  deleted with a name and a reason (it leaves retrieval, stays readable, and is logged
  in a Deleted section). Cases are only retrieved for the sections they have findings
  in, so a Fire lesson never reaches a Motor assessment.

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
`sample_data/` works well. Confirm the needs table (every required section needs a sum
insured), change a rating on the price page and watch the premium move, open the review
drill-down to say why, override a loading and see it disclosed, sign as "checked by" and
approve. Assess a similar client and watch the next finding cite the precedent case —
with your correction quoted in the prompt.

Once a case is approved, **Save PDF copy** on the decision page (or `GET /cases/{id}/pdf`)
downloads the insurer-facing document: `app/templates/case_pdf.html` rendered and converted
with xhtml2pdf (pure Python, no browser needed). Part 1 is the quotation (itemised
sections, total, terms, "Prepared by"); Part 2 the risk assessment behind it — findings per section
as title, severity and reasoning. Internal material — factor slugs, precedent ids, confidence,
evidence quotes, reviewer edits, loading overrides — is left out.

**Reset** on the case-memory page (`POST /demo/reset`) empties case memory, deleted
history included.

## Choosing the AI

The vendor lives in one file, `app/llm.py`, picked from the environment:

| Environment | Engine |
|---|---|
| `GEMINI_API_KEY` set | Google Gemini (`gemini-2.5-pro` / `-flash`) — the default for this project |
| `ANTHROPIC_API_KEY` set | Claude (`claude-opus-4-8` / `claude-haiku-4-5`) |
| neither, `claude` CLI on PATH | Claude Code CLI on the machine's existing login — keyless, for local prompt iteration only |

`LLM_PROVIDER`, `LLM_MODEL_MAIN`, `LLM_MODEL_FAST` override the defaults; `UW_CLI_TIMEOUT_S`
(default 240) bounds a CLI call. "Main" handles needs determination and assessment;
"fast" handles profile extraction, precedent retrieval and chat ingestion.
Every call's tokens (and cost, where the provider reports it) are captured and
shown on the price page. Adding a provider is one `_<name>_generate()` function in
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
  assess.py        per-section assessment (prompt = section scope + precedents with corrections + document)
  guardrails.py    deterministic evidence check, severity bands (case + per section), referrals
  pricing.py       deterministic pricing engine (sum insured × rate × band loading) — no LLM
  memory.py        SQLite case store, section-scoped retrieval, soft delete
  main.py          FastAPI routes;  report.py + templates/  HTML rendering
  pdf.py           insurer-facing PDF of an approved case (templates/case_pdf.html + xhtml2pdf)
  ingest_chats.py  seed memory (provisional) from historical chats;  evaluate.py  eval harness
config/            rates.json (base rate per section) + loadings.json (band → loading %) —
                   git-tracked, editable on /rates, placeholders until the broker's rate sheet
data/              cases.db  (git-ignored; safe to delete)
sample_data/       example application, blank broker intake sheet (PDF + text), example
                   PDF output, synthetic historical chats
tests/             sections, needs, guardrails, memory, flow, review, UI, PDF, learning loop
                   (LLM faked — offline)
Needs Analysis.pdf the broker needs analysis that sections.py transcribes
```
