# Solution Design — Converge Underwriting

**Status:** Implemented — v1.4, 2026-08-27. [ARCHITECTURE.md](ARCHITECTURE.md) is the
as-built map; the [README](../README.md) covers running, configuring and testing.
**History:** the original fixed-schema + deterministic-rules pipeline was removed
entirely (client decision, 2026-07-09): an LLM is required and the app fails fast at
startup without one. What survives of that philosophy is `guardrails.py` (§4.3).
The needs-determination gate, per-section assessment and the removal of every numeric
score followed on 2026-08-26; the client-facing PDF export on 2026-08-27.
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
4. **Assess, never price.** No premium, rate, sum insured, probability or score
   anywhere in the output — a standardised categorical severity and a derived
   referral band only.

Non-goals for the POC: multi-tenant auth, production-grade vector search,
fine-tuning, real-time chat integration.

## 2. Core concept — learning without training

LLM weights are frozen; the *context window* is not. "Learning" is implemented
as **what we retrieve into the prompt**:

| Memory layer | Analogy | Contents | Injected |
|---|---|---|---|
| **Case memory** | episodic memory | One record per past case: client profile, confirmed needs, draft and approved findings, corrections with the reviewer's why-notes | Top-k comparable cases, filtered to the section being assessed |
| **Playbook** | semantic memory / learned rules | Compact natural-language lessons distilled from reviewer corrections (`playbook.md`, versioned) | The rules tagged for the section being assessed, plus general ones |
| **Guardrails** | procedure | Deterministic validation: evidence check, citation allow-list, band mapping, referral triggers | Code, not prompt |

The loop itself is drawn in the README and, file by file, in ARCHITECTURE.md.
Two properties matter for the pitch to insurers:

- **Auditable.** Every finding cites its verbatim evidence, the precedent cases,
  and/or the playbook rule that influenced it. The playbook is a human-readable
  markdown file an underwriter can open, audit, and edit.
- **Immediate.** A reviewer correction takes effect on the very next
  assessment — demoable live, unlike fine-tuning.

**Governance rule: only human-approved material enters memory.** Unreviewed
LLM drafts never feed their own retrieval, and the playbook only changes when
an underwriter accepts a proposed edit, so errors can't compound. Human
sign-off *is* the learning signal.

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
`precedent_case_ids` / `playbook_rule_ids` it drew on (both empty = novel), and
a 0–1 `confidence`. There is deliberately no points field — see §6.3.

### 3.3 CaseRecord (the unit of memory)

`case_id`, `created_at`, `source` (`assessment` | `chat_ingestion`), the slim
`client_profile`, a retrieval `summary`, the confirmed `needs`, `draft_findings`
vs `approved_findings`, the `corrections` diff between them (each carrying the
reviewer's own why-note verbatim), the derived `final_band`, and a
`provisional` flag that keeps chat-ingested cases out of retrieval until a
human confirms them (§4.4). Stored as one JSON row in SQLite.

### 3.4 Playbook

`data/playbook.md`, copied to `data/playbook_history/` on every save. Each
rule is a markdown block:

```markdown
## PB-014 · [fire] Food service — gas installations
Absence of a gas installation certificate of conformity has been rated HIGH in
every reviewed food-service case. Treat as HIGH by default; cite the certificate
requirement in the finding.
Supporting cases: C-0032, C-0041, C-0057, C-0061
```

Rule IDs are stable so findings can cite them; the `[section-id]` tag routes
the rule to the right per-section prompt (`[general]` or untagged rules reach
every section); supporting-case links let an underwriter audit any rule back
to its evidence.

## 4. Components

### 4.1 `assess.py` — the assessment calls

A cheap "fast" call first extracts the `ClientProfile` — needed *before* the
main calls to drive retrieval. Then **one "main" call per section the
underwriter confirmed as required**, run concurrently, each assembled as:

```
[system]   role + section number, name and scope from the needs analysis
           + why this section is in scope (+ Motor sub-type, if Motor)
           + output rules + the no-pricing boundary
           + THE PLAYBOOK, filtered to this section
[user]     precedent findings under this section (from the top-k cases)
           + the raw application document
```

Findings come back tagged with the section and are reassembled in
needs-analysis order. One failed section fails the whole assessment — no
partial drafts. Prompt caching is not used yet; if it is, the section-filtered
playbook is the natural cacheable prefix since it changes only on reflection.

### 4.2 `memory.py` — storage, retrieval, reflection

- **Store:** SQLite, single `cases` table with the record as a JSON column
  (rationale in §6.2).
- **Retrieve:** a "fast" model reads one-line summaries of every active
  (non-provisional) case and picks the k most comparable (default k=5).
  Retrieval failure returns no precedents rather than failing the assessment.
- **Reflect:** after each human sign-off, one "main" call receives the
  approved case with its corrections and the current playbook and returns an
  edited playbook (add rule / strengthen / weaken / retire, section-tagged).
  It is only a **proposal**: the underwriter sees the diff, can edit it, and
  must accept it before it is saved (§6.5).

### 4.3 `guardrails.py` — the deterministic layer

The old rules-engine philosophy survives here, re-scoped to verification:

- drop findings whose `evidence_quote` does not appear (normalised) in the
  source document — kills hallucinated evidence — and findings whose quote is
  too short or made of stopwords ("Yes") to evidence anything;
- strip precedent / rule citations the model was not actually given, and note
  that it happened;
- derive the referral band from the severity profile: High for any severe or
  3+ high, Elevated for any high or 3+ medium, Moderate for any medium, Low
  otherwise;
- refer to a human when a finding is severe, cites nothing (novel), or has
  confidence below 0.6, and whenever citations were stripped or findings
  dropped.

An underwriter can reproduce the band by hand; what changed from the legacy
design is that the findings list comes from precedent + playbook rather than
fixed rules, and there is no arithmetic at all.

### 4.4 `ingest_chats.py` — bootstrapping from historical chats

One-off batch over exported chat transcripts, one "fast" call each: extract
the client profile and the risks the human underwriter actually decided on;
skip transcripts with no risk decision. Each result is stored as a
**provisional** `CaseRecord` (`source="chat_ingestion"`): invisible to
retrieval until a human confirms it on `/cases`, and ingestion never writes to
the playbook. That keeps the "only approved data enters memory" rule honest
even for machine-extracted history.

### 4.5 The three gates in the UI

FastAPI + Jinja, single implicit reviewer, no auth:

1. **Needs table** — the underwriter can re-bucket any section and pick the
   Motor sub-type; at least one section must be required.
2. **Review** — split-screen draft with the source document: change a
   severity, remove a finding, add one (subject to the same evidence check),
   and say why on each edit. Approve stores the case and triggers reflection.
3. **Learning** — the proposed playbook, editable, with accept / skip. The
   approved case is a precedent either way.

The decision page then offers a client-facing PDF (`pdf.py`, xhtml2pdf) that
omits internal codes — factor slugs, rule and precedent ids, confidence,
reviewer edits.

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
no-pricing boundary. Named per-field rules are gone.

### 6.4 ⚖️ Reflection cadence — synchronous per sign-off vs batched
Per sign-off is what is built: it makes the demo interactive — correct one
case, assess a similar one, watch the lesson appear. Batched (nightly) is
cheaper and produces a calmer playbook at production volume; it would be a
small change since reflection is already one function over one case.

### 6.5 ⚖️ Playbook write access — LLM-drafted, human-owned
Implemented: the LLM drafts an editable playbook update after case approval, but
the update only becomes active when the underwriter explicitly accepts it. The
underwriter can edit or skip the proposal, and the previous version is archived.

### 6.6 ⚖️ Precedent scope — global memory vs per-insurer partitions
If this is pitched to multiple insurers, does insurer A's correction history
teach the system serving insurer B? Cross-tenant learning is a data-governance
question the client must answer before production. POC: single shared memory.

### 6.7 ✅ Cold start / novel risks
A finding citing no precedent and no playbook rule is allowed but auto-flagged
`NOVEL` and referred. Early on most findings are novel; as memory fills,
referral rate drops — which is itself a nice "the system is learning" metric
to chart in the demo.

### 6.8 ✅ Memory hygiene
Reflection can retire rules (contradicted by newer decisions), and rules carry
supporting-case links so stale ones are traceable. The playbook is capped at
~2500 tokens; when exceeded, reflection must consolidate before adding.

### 6.9 ⚖️ Evaluation — how do we prove it's learning?
`python -m app.evaluate`: for every stored case, rebuild a pseudo-application
from its evidence and assess it leave-one-out with memory off vs on, counting
approved findings recovered (and severities matched). One number
("precedent-informed assessments matched historical underwriter decisions X%
vs Y% blind") carries the pitch. Caveat: playbook rules the held-out case
contributed remain in force.

### 6.10 ✅ Models
Two tiers, not two vendors: "main" for needs determination, assessment and
reflection (quality-critical); "fast" for profile extraction, retrieval and
chat ingestion. The provider and the per-tier model names are environment
configuration — see the README.

### 6.11 ✅ Per-section assessment, not one whole-submission call
One call per required section keeps each prompt focused (its own scope, its
own rules, its own precedents), lets the calls run concurrently, and makes the
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
| 5 | Reflection step, gated by the underwriter | done |
| 6 | `ingest_chats.py` + synthetic historical-chat dataset, provisional until confirmed | done |
| 7 | Eval harness + demo script ("correct → re-assess → watch it learn") | done |
| 7b | Needs determination gate, 18-section catalogue, per-section assessment, no score | done (2026-08-26) |
| 7c | Client-facing PDF export | done (2026-08-27) |
| 8 | (optional) swap retriever to `voyage-4-lite` embeddings | open |

## 8. Risks

- **Playbook drift / overgeneralization** — a lesson learned from 2 cases
  stated as a universal rule. Mitigated by supporting-case links, the
  section tag, and the human-visible diff every change goes through (§6.5,
  §6.8).
- **Sparse chat data** — if historical transcripts are few or low-signal,
  seed the demo with synthetic-but-realistic transcripts and say so (the
  bundled `sample_data/chats/` are synthetic).
- **Reviewer fatigue** — the learning loop is only as good as the corrections;
  approve-with-no-edits is one click so the happy path is cheap.
- **Insurer skepticism of LLM-proposed factors** — the counter is the audit
  chain (evidence quote → precedent → playbook rule → human sign-off), which
  the review page puts front-and-center.
- **Over-inclusive needs tables** — a model that marks everything required
  puts the client on cover they cannot claim under. The needs prompt pushes
  back on this explicitly, and gate 1 exists so the underwriter has the last
  word.
