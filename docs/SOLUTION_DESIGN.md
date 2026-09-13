# Solution Design — Converge Underwriting

**Status:** Implemented — v1.5, 2026-09-12. [ARCHITECTURE.md](ARCHITECTURE.md) is the
as-built map; the [README](../README.md) covers running, configuring and testing.
**History:** the original fixed-schema + deterministic-rules pipeline was removed
entirely (client decision, 2026-07-09): an LLM is required and the app fails fast at
startup without one. What survives of that philosophy is `guardrails.py` (§4.3).
The needs-determination gate, per-section assessment and the removal of every numeric
score followed on 2026-08-26; the client-facing PDF export on 2026-08-27. On 2026-09-12
(client meeting of 2026-09-01) the playbook and its reflection gate were removed: case
memory — with the reviewer's corrections carried inside each precedent — is the only
learning layer, and the Price gate became the approval gate.
**Deferred as designed:** embeddings (§5) — retrieval is LLM-as-picker behind one
`retrieve()` function (§6.1).

---

## 1. Goals

Per the client's requirements:

1. **Open-ended risk discovery.** The LLM reads the raw application and decides
   its own risk factors, instead of populating a fixed field dictionary that a
   hand-written rules engine scores.
2. **A self-learning system.** Assessments should visibly improve from (a) the
   client's historical chats / past risk decisions and (b) corrections made by
   human reviewers going forward — without training or fine-tuning a model.
3. **Needs before risk.** Work out which of the 18 cover sections (from the
   broker needs analysis) a business actually needs, and let the underwriter
   confirm that before anything is assessed.
4. **The model assesses; the engine prices.** The LLM never produces a
   premium, rate, probability or score — a standardised categorical severity
   and a derived band only. Premiums come from a separate deterministic
   pricing engine (`pricing.py`, added 2026-08-31 after the broker meeting of
   2026-08-30): sum insured x broker base rate x band loading, reproducible
   by hand, with sums insured confirmed by the broker at gate 1.

Non-goals for the POC: multi-tenant auth, production-grade vector search,
fine-tuning, real-time chat integration.

## 2. Core concept — learning without training

LLM weights are frozen; the *context window* is not. "Learning" is implemented
as **what we retrieve into the prompt**:

| Memory layer | Analogy | Contents | Injected |
|---|---|---|---|
| **Case memory** | episodic memory | One record per past case: client profile, confirmed needs, draft and approved findings, corrections with the reviewer's why-notes, who checked it, its pricing | Top-k comparable cases among those with findings in the sections being assessed; each section's prompt sees that section's findings plus the reviewer's changes to them |
| **Guardrails** | procedure | Deterministic validation: evidence check, citation allow-list, band mapping, referral triggers | Code, not prompt |

The loop itself is drawn in the README and, file by file, in ARCHITECTURE.md.
Two properties matter for the pitch to insurers:

- **Auditable.** Every finding cites its verbatim evidence and the precedent
  cases that influenced it; every precedent carries the reviewer's own
  corrections, so a lesson is always one hop from the decision that taught it.
- **Immediate.** A reviewer correction takes effect on the very next
  assessment — demoable live, unlike fine-tuning.

**Governance rule: only human-approved material enters memory.** Unreviewed
LLM drafts never feed their own retrieval: a case enters memory only when the
underwriter signs it off at the Price gate with "add to case memory" ticked,
so errors can't compound. Human sign-off *is* the learning signal. There is no
separate rule layer to drift: a lesson lives and dies with the case that
taught it, and a case can be deleted (with a name and a reason) when it
should no longer teach.

## 3. Data model

The shapes live in `app/models.py` (and the section catalogue in
`app/sections.py`); this is the reasoning behind them, in pipeline order.

### 3.1 SectionNeed / NeedsDetermination

One row per cover section: `required | consider | not-applicable`, a one-line
reason grounded in the submission, and a Motor sub-type when Motor is in play.
The model must return exactly one row per section; `needs.py` repairs any it
skips as `consider` with an honest reason rather than inventing or dropping it.
The confirmed table is stored on the case, so evaluation later assesses the
same ground the human did.

### 3.2 RiskFinding

The LLM stays on rails about *shape*, not *content*: a snake_case
`factor_name` of its own choosing, the `section` it was assessed under, a
`severity` on the standardised low / medium / high / severe scale, a narrative
`assessment_note` naming the reference class ("below standard for a
food-production occupancy"), a **verbatim** `evidence_quote`, reasoning, the
`precedent_case_ids` it drew on (empty = novel), and a 0–1 `confidence`.
There is deliberately no points field — see §6.3.

### 3.3 CaseRecord (the unit of memory)

`case_id`, `created_at`, `source` (`assessment` | `chat_ingestion`), the slim
`client_profile`, a retrieval `summary`, the confirmed `needs`, `draft_findings`
vs `approved_findings`, the `corrections` diff between them (each carrying the
reviewer's own why-note verbatim), the derived `final_band`, `checked_by`
(the underwriter who approved at the Price gate), the `pricing` table, a
`provisional` flag that keeps a case out of retrieval until a human confirms
it (chat-ingested cases, and cases approved with "add to case memory"
unticked — §4.4), and the soft-delete trio `deleted_at` / `deleted_by` /
`deleted_reason`. Stored as one JSON row in SQLite.

### 3.4 Corrections are the lesson

There is no distilled rule layer. When a precedent case is rendered into a
section's prompt, its approved findings for that section are followed by the
reviewer's changes to that section, verbatim:

```
Case C-0032 — Restaurant with a gas kitchen; covers: Fire
  Outcome: Elevated band
  - uncertified_gas_installation [high] No certificate of conformity since the refit.
  Reviewer changes: severity_changed uncertified_gas_installation medium→high
  ("Gas plus no certificate is never medium.")
```

A Fire lesson reaches only Fire prompts, because corrections are scoped to the
section of the finding they changed, and a case is only a retrieval candidate
for the sections it has findings in. Removing a lesson means deleting (or
re-approving) the case that carries it — nothing to retag, renumber or retire.

## 4. Components

### 4.1 `assess.py` — the assessment calls

A cheap "fast" call first extracts the `ClientProfile` — needed *before* the
main calls to drive retrieval. Then **one "main" call per section the
underwriter confirmed as required**, run concurrently, each assembled as:

```
[system]   role + section number, name and scope from the needs analysis
           + why this section is in scope (+ Motor sub-type, if Motor)
           + output rules + the no-pricing boundary
[user]     precedent findings under this section (from the top-k cases),
           each followed by the reviewer's changes and why-notes (§3.4)
           + the raw application document
```

Findings come back tagged with the section and are reassembled in
needs-analysis order. One failed section fails the whole assessment — no
partial drafts. Prompt caching is not used yet; if it is, the system prompt
(fixed per section) is the natural cacheable prefix.

### 4.2 `memory.py` — storage, retrieval, deletion

- **Store:** SQLite, single `cases` table with the record as a JSON column
  (rationale in §6.2).
- **Retrieve:** called after gate 1 with the confirmed sections. Candidates
  are the active (non-provisional, non-deleted) cases with at least one
  approved finding in any of those sections; a "fast" model reads their
  one-line summaries, is told which sections are being assessed, and picks
  the k most comparable (default k=5). Retrieval failure returns no
  precedents rather than failing the assessment.
- **Delete:** soft. The row keeps `deleted_at` / `deleted_by` /
  `deleted_reason`, leaves retrieval and the case list, and appears in the
  Deleted log on `/cases`. Case IDs count deleted rows, so an ID is never
  reused. Restore is deliberately absent (open per client).

### 4.3 `guardrails.py` — the deterministic layer

The old rules-engine philosophy survives here, re-scoped to verification:

- drop findings whose `evidence_quote` does not appear (normalised) in the
  source document — kills hallucinated evidence — and findings whose quote is
  too short or made of stopwords ("Yes") to evidence anything;
- strip precedent citations the model was not actually given, and note that
  it happened;
- derive the referral band from the severity profile: High for any severe or
  3+ high, Elevated for any high or 3+ medium, Moderate for any medium, Low
  otherwise;
- refer to a human when a finding is severe, cites nothing (novel), or has
  confidence below 0.6, and whenever citations were stripped or findings
  dropped.

An underwriter can reproduce the band by hand; what changed from the legacy
design is that the findings list comes from precedent rather than fixed
rules, and there is no arithmetic at all.

### 4.4 `ingest_chats.py` — bootstrapping from historical chats

One-off batch over exported chat transcripts, one "fast" call each: extract
the client profile and the risks the human underwriter actually decided on;
skip transcripts with no risk decision. Each result is stored as a
**provisional** `CaseRecord` (`source="chat_ingestion"`): invisible to
retrieval until a human confirms it on `/cases`. The same flag serves a case
the underwriter approves with "add to case memory" unticked. That keeps the
"only approved data enters memory" rule honest even for machine-extracted
history.

### 4.5 The two gates in the UI

FastAPI + Jinja, single implicit reviewer, no auth:

1. **Needs table** — the underwriter can re-bucket any section (required /
   not-applicable), pick the Motor sub-type, and confirm or correct the
   pre-filled sum insured per required section; at least one section must be
   required, and **every required section must have a sum insured** — the
   form is sent back otherwise, so every line downstream is priced. Sums are
   pre-filled by a fast extraction call (`sums.py`) that only transcribes
   figures the submission states — the confirmed number is the only one ever
   priced.
2. **Price** — the approval gate. Per required section: the premium row
   (`pricing.py`: sum insured x base rate, loading picked from the band table
   by the section's band — guardrails.band_for_section over that section's
   findings) and, under it, the findings as **identifier · rating ·
   description**. Changing a rating re-bands the section and re-picks its
   loading in the browser (the band rule and the loading table are mirrored
   client-side) — live totals, no model call; a loading the underwriter typed
   survives a band change, a table loading follows it. **Checked by** is
   required; **Add to case memory** (default on) decides whether the case is
   a precedent or stays provisional. Approve recomputes everything
   server-side, records rating edits as `severity_changed` corrections, stores
   the case and shows the report.

   *Review findings & evidence* is a drill-down from the Price gate: the
   split-screen page with the source document, where a finding can be removed
   or added (subject to the same evidence check) with a why-note on each
   edit. *Save & go back* writes the edits into the draft; nothing is stored
   until the Price gate's approve.

The decision page is the insurer document, and the PDF (`pdf.py`, xhtml2pdf)
mirrors it: Part 1 the quotation — itemised sections (sum insured,
rate, loading, premium), total, terms, **Prepared by** — and Part 2 the risk
assessment behind it, one statement per finding (title, severity, reasoning).
Internal material — factor slugs, precedent ids, confidence, evidence quotes,
reviewer edits, loading overrides — stays on the review and pricing pages and
in the case record. Pricing of a stored case can be adjusted afterwards
(loadings only; ratings are fixed once approved).

### 4.6 `pricing.py` — the deterministic pricing engine

No LLM, like guardrails.py: `premium = sum insured x rate x (1 + loading)`.
Base rates (annual % of sum insured, flat per section) live in
`config/rates.json`; the band -> loading table (one global table, negative
values discount) in `config/loadings.json`. Both are git-tracked, created
with placeholder values on first use (placeholders stand in until the
broker's rate sheet arrives), and editable on the `/rates` page.
`band_for_section()` in guardrails.py is deliberately the *single* seam for
section rating: crediting mitigation factors later changes that one function
and nothing downstream.

## 5. Embeddings

### 5.1 What they are

An embedding model maps a piece of text to a vector (e.g. 1024 floats) such
that semantically similar texts land close together. "Panel beater, 8 staff,
single workshop, spray booth on site" and "auto body repair shop with paint
spraying" embed near each other despite sharing almost no words — which is
exactly what keyword search misses. We embed each case's summary once at store
time, embed the new client's profile at assessment time, and rank by cosine
similarity. That's the entire retrieval engine; no vector database required at
this scale (see §6.2).

### 5.2 Voyage AI (Anthropic's recommended provider)

Anthropic doesn't ship its own embedding model; their docs point to **Voyage
AI** (MongoDB-owned). Current lineup (Voyage 4 generation, Jan 2026 — all 32k
context, 1024-dim default with 256/512/2048 options):

| Model | Position | Fit for us |
|---|---|---|
| `voyage-4-large` | best retrieval quality | overkill at POC scale |
| `voyage-4` | balanced quality/cost | fine default |
| **`voyage-4-lite`** | cheapest/fastest | **recommended** — case summaries are short, easy texts |
| `voyage-4-nano` | open-weight (Apache 2.0, on Hugging Face) | escape hatch if data-residency ever blocks API use |
| `voyage-finance-2` | finance/insurance domain-tuned | worth an A/B once there's an eval set |

Use `input_type="document"` when embedding stored cases and
`input_type="query"` when embedding the incoming profile — Voyage prepends
different retrieval prompts for each and it measurably helps.

### 5.3 Alternatives

| Option | Examples | Trade-off vs Voyage |
|---|---|---|
| Other API providers | OpenAI `text-embedding-3-small/large`, Cohere Embed v4, Google Gemini embeddings | Comparable quality tier; adds a second/other vendor. OpenAI's is the cheapest common choice; Cohere is strong multilingual. Gemini embeddings would keep this project single-vendor. |
| Open-source, self-hosted | `voyage-4-nano`, BGE-M3, `nomic-embed-text`, E5, any `sentence-transformers` model | Zero per-call cost, data never leaves your infra (relevant if SA client-data residency comes up). Cost: you run the model (~0.5–2GB, CPU is fine at this scale) and quality is a notch below the paid APIs. |
| **No embeddings at all — LLM-as-retriever** (what is built) | the "fast" model picks the k most relevant cases from a list of one-line case summaries | At ≤ ~200 cases, one cheap call per assessment does the job with zero infrastructure and *better* relevance judgment than cosine similarity (it can reason about why a case is comparable). Stops scaling around several hundred cases. |
| Keyword/BM25 | SQLite FTS5 | Free, built into SQLite, surprisingly strong on jargon-heavy text. Misses paraphrases. Good as a *hybrid* companion to embeddings, unnecessary alone. |

**Recommendation:** LLM-as-retriever for now — zero moving parts, best demo
relevance. Add `voyage-4-lite` embeddings behind the same `retrieve()`
interface when the case count or latency justifies it; `memory.py` isolates
retrieval so this is a local change, not a rewrite.

### 5.4 Cost, hosting, and the embeddings build-out

**Hosting: there is nothing to host.** Voyage is a REST API exactly like the
Anthropic API — `pip install voyageai`, set `VOYAGE_API_KEY`, call
`vo.embed(texts, model=..., input_type=...)`. No model runs on our
infrastructure. For enterprises that require it, Voyage also offers VPC
deployment via AWS/Azure Marketplace, and `voyage-4-nano` is open-weight
(Apache 2.0) for fully self-hosted setups — both are compliance escape
hatches, not POC concerns.

**Cost: effectively zero at this scale.** Pricing is usage-based per million
tokens, with a large free allowance per model (as of 2026-07):

| Model | $/1M tokens | Free tier |
|---|---|---|
| `voyage-4-lite` | $0.02 | 200M tokens |
| `voyage-4` | $0.06 | 200M tokens |
| `voyage-4-large` | $0.12 | 200M tokens |
| `voyage-finance-2` | $0.12 | 50M tokens |

A case summary is ~150 tokens, so the 200M free tokens cover ~1.3M case
embeddings — the POC and years of production volume never leave the free
tier. Model choice is therefore about quality/latency, not cost. (A Batch API
with a 33% discount exists for bulk backfills; irrelevant under the free tier.)

**Build-out when the time comes** (Phase 8):

1. Implement an embedding retriever alongside the existing LLM picker behind
   the same `retrieve(profile, k)` interface.
2. Add an `embedding` column (SQLite BLOB) to the `cases` table and backfill:
   embed every stored case's `summary` + profile text with
   `input_type="document"`.
3. On `store()`, embed the new case at write time (one API call per approval).
4. On `retrieve()`, embed the incoming profile with `input_type="query"`,
   brute-force cosine (numpy dot product — Voyage vectors are unit-normalized)
   over all stored vectors, apply the industry/cover filters, return top-k.
5. Flip the config flag. Re-running the eval harness (§6.9) with both
   retrievers is the acceptance test.

**On `voyage-finance-2`:** tuned for finance documents (filings, earnings
calls) — adjacent to insurance underwriting text, not its core domain — and
it's a previous-generation (2024) model, so the general-purpose `voyage-4`
family likely matches or beats it here. Don't default to it; A/B it against
`voyage-4-lite` on the eval set in Phase 8 and let the numbers decide.

## 6. Decisions & trade-offs

Decisions marked ✅ are settled defaults; ⚖️ were, or still are, the client's
call.

### 6.1 ✅ Retrieval strategy — staged (LLM-picker → embeddings)
See §5.3. The interface hides the choice; upgrade when scale demands.

### 6.2 ✅ Storage — SQLite, not a vector DB
At POC scale (≲ thousands of cases), brute-force cosine over an in-memory
numpy matrix is sub-millisecond. A vector DB (Pinecone, Qdrant, pgvector)
buys nothing yet and adds ops surface to a demo. pgvector on Postgres is the
natural production step if this graduates.

### 6.3 ⚖️ Who scores — nobody; LLM proposes, guardrails band, human approves
Options were (a) keep deterministic scoring and only let the LLM *find*
factors, (b) let the LLM score freely, (c) a hybrid where the LLM suggested
points and guardrails capped them. The client went further than (c): **no
numeric score at all** (2026-08-26), because anything numeric reads as a
price or a rating. Severity is a standardised categorical scale used
identically across sections and cases, the referral band is a deterministic
lookup over the severity profile (§4.3), and every prompt carries an explicit
no-pricing boundary. Named per-field rules are gone. The 2026-08-31 pricing
engine does not weaken this: premiums are computed *after* approval by plain
Python (§4.6) from broker-confirmed inputs — the LLM still never emits a
number.

### 6.4 ⚖️ One learning layer, not two (2026-09-12)
Until v1.4 corrections were also distilled by an LLM into a section-tagged
playbook that the underwriter accepted at a fourth gate. The client retired
it: the extra gate slowed the flow, and a rule distilled from two cases read
as policy. Corrections now travel verbatim inside the precedent text (§3.4),
which keeps the "correct one case, assess a similar one, see the lesson"
demo intact with one fewer model call and no rule file to govern.

### 6.5 ⚖️ Price is the approval gate (2026-09-12)
Underwriters wanted to rate and price in one place, so the findings table
(identifier · rating · description) sits under each premium row and the
review page became a drill-down for evidence and add/remove. Ratings are
therefore approved by the same click as the loadings, under a named
"checked by".

### 6.6 ⚖️ Precedent scope — global memory vs per-insurer partitions
If this is pitched to multiple insurers, does insurer A's correction history
teach the system serving insurer B? Cross-tenant learning is a data-governance
question the client must answer before production. POC: single shared memory.

### 6.7 ✅ Cold start / novel risks
A finding citing no precedent is allowed but auto-flagged `NOVEL` and referred. Early on most findings are novel; as memory fills,
referral rate drops — which is itself a nice "the system is learning" metric
to chart in the demo.

### 6.8 ✅ Memory hygiene
A case that should no longer teach is deleted with a name and a reason (soft
delete: it leaves retrieval and the listing, stays readable, and is logged on
`/cases`). Because a lesson lives inside its case, that is the whole
retirement mechanism. Restore is deliberately absent until a client asks.

### 6.9 ⚖️ Evaluation — how do we prove it's learning?
`python -m app.evaluate`: for every stored case, rebuild a pseudo-application
from its evidence and assess it leave-one-out with memory off vs on, counting
approved findings recovered (and severities matched). One number
("precedent-informed assessments matched historical underwriter decisions X%
vs Y% blind") carries the pitch.

### 6.10 ✅ Models
Two tiers, not two vendors: "main" for needs determination and assessment
(quality-critical); "fast" for profile extraction, retrieval and chat
ingestion. The provider and the per-tier model names are environment
configuration — see the README.

### 6.11 ✅ Per-section assessment, not one whole-submission call
One call per required section keeps each prompt focused (its own scope, its
own precedents), lets the calls run concurrently, and makes the
needs table the single control over what gets assessed. The cost is more
calls per submission and the loss of cross-section reasoning, which the
prompt explicitly tells the model to leave to the other sections.

## 7. Build plan

| Phase | Deliverable | Status |
|---|---|---|
| 1 | `RiskFinding`/`CaseRecord` schemas + `assess.py` with empty memory | done |
| 2 | `guardrails.py` (evidence check, band, referrals) + report shows findings w/ evidence | done |
| 3 | `memory.py` store + LLM-as-retriever; assess cites precedents | done |
| 4 | Review UI (edit + approve) + case persistence on approval | done |
| 5 | Reflection step, gated by the underwriter | done; retired 2026-09-12 (§6.4) |
| 6 | `ingest_chats.py` + synthetic historical-chat dataset, provisional until confirmed | done |
| 7 | Eval harness + demo script ("correct → re-assess → watch it learn") | done |
| 7b | Needs determination gate, 18-section catalogue, per-section assessment, no score | done (2026-08-26) |
| 7c | Client-facing PDF export | done (2026-08-27) |
| 7d | Deterministic pricing engine + Price gate | done (2026-08-31) |
| 7e | Playbook removed; Price gate is the approval gate; section-scoped retrieval; soft delete | done (2026-09-12) |
| 8 | (optional) swap retriever to `voyage-4-lite` embeddings | open |

## 8. Risks

- **Precedent overreach** — one reviewer's correction read as a universal
  rule. Mitigated by scoping: a case is only retrieved for sections it has
  findings in, each prompt sees only that section's findings and changes, and
  the picker reasons about comparability rather than keyword overlap. A case
  that misleads can be deleted (§6.8).
- **Sparse chat data** — if historical transcripts are few or low-signal,
  seed the demo with synthetic-but-realistic transcripts and say so (the
  bundled `sample_data/chats/` are synthetic).
- **Reviewer fatigue** — the learning loop is only as good as the corrections;
  approve-with-no-edits is one click so the happy path is cheap.
- **Insurer skepticism of LLM-proposed factors** — the counter is the audit
  chain (evidence quote → precedent → reviewer correction → human sign-off),
  which the review drill-down puts front-and-center.
- **Over-inclusive needs tables** — a model that marks everything required
  puts the client on cover they cannot claim under. The needs prompt pushes
  back on this explicitly, and gate 1 exists so the underwriter has the last
  word.
