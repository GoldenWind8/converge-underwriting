# Solution Design — Self-Learning Risk Assessment

**Status:** Implemented — v1.2, 2026-07-09 (see [ARCHITECTURE.md](ARCHITECTURE.md) for the as-built map)
**Supersedes:** the fixed-schema + deterministic-rules design described in the README —
that legacy pipeline has been **removed entirely** (client decision, 2026-07-09): an LLM
is required and the app fails fast at startup without a key. What survives of the old
philosophy is guardrails.py (§4.3).
**Implementation notes:** the LLM provider is swappable via `app/llm.py` — Gemini is the
project default (client has a key), Anthropic is the alternative. Tests fake the LLM so
they run offline. Embeddings (§5) were deferred as designed: retrieval is LLM-as-picker
behind one `retrieve()` function (§6.1).

---

## 1. Goals

Per the client's updated requirements:

1. **Open-ended risk discovery.** The LLM reads the raw application and decides
   its own risk factors, instead of populating a fixed field dictionary that a
   hand-written rules engine scores.
2. **A self-learning system.** The system's assessments should visibly improve
   from (a) the client's historical client chats / past risk decisions and
   (b) corrections made by human reviewers going forward — without training or
   fine-tuning a model.

Non-goals for the POC: multi-tenant auth, production-grade vector search,
fine-tuning, real-time chat integration.

## 2. Core concept — learning without training

LLM weights are frozen; the *context window* is not. "Learning" is implemented
as **what we retrieve into the prompt**:

| Memory layer | Analogy | Contents | Injected |
|---|---|---|---|
| **Case memory** | episodic memory | One record per past assessment: client profile, risks found, severities, evidence, human-approved outcome, corrections | Top-k similar cases, retrieved per assessment |
| **Playbook** | semantic memory / learned rules | Compact natural-language lessons distilled from cases and reviewer corrections (`playbook.md`, versioned) | Whole file, every assessment |
| **Guardrails** | procedure | Deterministic validation: envelope schema, point caps, band mapping, referral triggers | Code, not prompt |

The loop that makes it "self-learning":

```
                      ┌──────────── retrieve top-k similar cases ────────────┐
                      │                                                      │
 raw application ──▶ ASSESS (LLM proposes risk findings) ◀── playbook.md     │
                      │                                                      │
                      ▼                                                      │
              draft findings + score                                         │
                      │                                                      │
                      ▼                                                      │
             GUARDRAILS (deterministic caps, band, referrals)                │
                      │                                                      │
                      ▼                                                      │
             HUMAN REVIEW (approve / edit severities / add-remove findings)  │
                      │                                                      │
        ┌─────────────┴─────────────┐                                        │
        ▼                           ▼                                        │
     REPORT                 store approved case ─────────────────────────────┘
                                    │
                                    ▼
                       REFLECT (LLM diffs draft vs approved,
                                updates playbook.md)
```

Two properties matter for the pitch to insurers:

- **Auditable.** Every finding cites the evidence quote, the precedent cases,
  and/or the playbook rule that influenced it. The playbook itself is a
  human-readable markdown file an underwriter can open, audit, and edit.
- **Immediate.** A reviewer correction takes effect on the very next
  assessment — demoable live, unlike fine-tuning.

**Governance rule: only human-approved assessments enter memory.** Unreviewed
LLM drafts never feed their own retrieval, so errors can't compound. Human
sign-off *is* the learning signal.

## 3. Data model

### 3.1 RiskFinding (replaces the fixed per-cover schemas)

The LLM stays on rails about *shape*, not *content*:

```python
class RiskFinding(BaseModel):
    factor_name: str          # LLM-chosen, e.g. "uncertified_gas_installation"
    section: str              # cover it affects: Fire / BI / PL / General / <other>
    severity: Severity        # info | low | medium | high
    suggested_points: int     # guardrails cap this per severity tier
    evidence_quote: str       # verbatim text from the source document
    reasoning: str            # why this is a risk for this client
    precedent_case_ids: list[str]   # which retrieved cases informed it ([] = novel)
    playbook_rule_ids: list[str]    # which playbook rules informed it
    confidence: float         # 0-1; low confidence forces a referral

class RiskAssessmentDraft(BaseModel):
    client_profile: ClientProfile   # slim: name, industry, size, covers requested
    findings: list[RiskFinding]
    overall_notes: list[str]
```

`ClientProfile` is a much slimmer extraction than today's
`UnderwritingSubmission` — enough to file, retrieve, and report on the case,
not an exhaustive field dictionary.

### 3.2 CaseRecord (the unit of memory)

```python
class CaseRecord(BaseModel):
    case_id: str
    created_at: datetime
    source: Literal["assessment", "chat_ingestion"]
    client_profile: ClientProfile
    summary: str                    # 1-2 sentence LLM-written description, used for retrieval
    draft_findings: list[RiskFinding]      # what the LLM proposed
    approved_findings: list[RiskFinding]   # what the human signed off
    corrections: list[Correction]          # structured diff draft → approved
    final_score: int
    final_band: str
    embedding: list[float] | None   # embedding of `summary` + profile text
```

`Correction` records `{type: added|removed|severity_changed|points_changed,
finding, reviewer_note}` — this is the raw material for reflection.

### 3.3 Playbook

`playbook.md`, checked into the data directory and versioned (git or a simple
copy-on-write history table). Structure:

```markdown
## PB-014 · Food service — gas installations   (confidence: high, 4 supporting cases)
Absence of a gas installation certificate of conformity has been rated HIGH in
every reviewed food-service case. Treat as HIGH by default; cite the certificate
requirement in the finding.
Supporting cases: C-0032, C-0041, C-0057, C-0061

## PB-015 · Single-location manufacturers   (confidence: medium, 2 supporting cases)
...
```

Rules carry stable IDs so findings can cite them, plus a confidence level and
supporting-case links so an underwriter can audit any rule back to its
evidence.

## 4. Components

### 4.1 `assess.py` — the assessment call (replaces extraction + rules as the scorer)

One Claude call (`claude-opus-4-8`, structured output via
`client.messages.parse` against `RiskAssessmentDraft`), prompt assembled as:

```
[system]   role + method + output rules + THE PLAYBOOK          ← cacheable prefix
[user]     top-k precedent cases (compact renderings)
           + the raw application document
```

Prompt-caching note: the playbook goes in the system prompt with a
`cache_control` breakpoint (it changes only on reflection, i.e. per sign-off,
not per request); precedents and the document go after it since they vary per
request.

A cheap pre-step extracts the `ClientProfile` (industry, covers, size) — needed
*before* the main call to drive retrieval filtering.

### 4.2 `memory.py` — storage, retrieval, reflection

- **Store:** SQLite, single `cases` table with a JSON column for the record and
  a BLOB for the embedding. (Rationale in §6.2.)
- **Retrieve:** filter by industry-adjacency + covers requested, then rank by
  cosine similarity of the case-summary embedding against the new client's
  profile text. Return top-k (default k=5).
- **Reflect:** after each human sign-off, one LLM call receives the correction
  diff + the current playbook and returns an edited playbook (add rule /
  strengthen confidence / weaken / retire). Human-visible diff logged.

### 4.3 `guardrails.py` — the demoted-but-kept deterministic layer

The existing `rules.py` philosophy survives here, re-scoped:

- validate the envelope (Pydantic — already forced by structured outputs);
- reject findings whose `evidence_quote` does not appear (fuzzily) in the
  source document → kills hallucinated evidence;
- cap `suggested_points` per severity tier; map total → band deterministically;
- force **referral to a human** when: confidence < threshold, a finding cites
  no precedent and no playbook rule (novel risk), or total score lands in a
  band boundary zone.

An underwriter can still reproduce the *score arithmetic* by hand; what changed
is that the findings list comes from precedent + playbook rather than fixed
rules.

### 4.4 `ingest_chats.py` — bootstrapping from historical chats

One-off batch job over the client's exported chat transcripts:

1. Per transcript, an LLM call extracts a `CaseRecord` with
   `source="chat_ingestion"`: client profile, which risks the human identified,
   the evidence phrases, the outcome. Transcripts with no risk decision are
   skipped.
2. Records are written to case memory (embedded + stored).
3. A reflection pass over the full ingested set produces `playbook.md` v1.
4. **Human spot-check step**: the client reviews a sample of ingested cases
   before the demo — keeps the "only approved data enters memory" rule honest.

Use the **Message Batches API** here (50% cost, transcripts aren't latency
sensitive).

### 4.5 Review UI

Extend the existing FastAPI app: the report page becomes an editable draft —
reviewer can change severity/points, delete findings, add findings, and must
click **Approve** before the case is stored and reflection runs. (POC: single
implicit reviewer, no auth.)

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
| Other API providers | OpenAI `text-embedding-3-small/large`, Cohere Embed v4, Google Gemini embeddings | Comparable quality tier; adds a second/other vendor. OpenAI's is the cheapest common choice; Cohere is strong multilingual. No strong reason to prefer any over Voyage in an Anthropic stack. |
| Open-source, self-hosted | `voyage-4-nano`, BGE-M3, `nomic-embed-text`, E5, any `sentence-transformers` model | Zero per-call cost, data never leaves your infra (relevant if SA client-data residency comes up). Cost: you run the model (~0.5–2GB, CPU is fine at this scale) and quality is a notch below the paid APIs. |
| **No embeddings at all — LLM-as-retriever** | Claude Haiku picks the k most relevant cases from a list of one-line case summaries | At ≤ ~200 cases, one cheap Haiku call per assessment does the job with zero infrastructure and *better* relevance judgment than cosine similarity (it can reason about why a case is comparable). Stops scaling around several hundred cases. |
| Keyword/BM25 | SQLite FTS5 | Free, built into SQLite, surprisingly strong on jargon-heavy text. Misses paraphrases. Good as a *hybrid* companion to embeddings, unnecessary alone. |

**Recommendation:** start with **LLM-as-retriever** (Haiku over summaries) for
week one — zero moving parts, best demo relevance. Add `voyage-4-lite`
embeddings behind the same `retrieve()` interface when the case count or
latency justifies it. Design `memory.py`'s retrieval as a swappable strategy so
this is a config change, not a rewrite.

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

1. Implement `EmbeddingRetriever` alongside the existing `LLMRetriever` behind
   the same `retrieve(profile, k)` interface.
2. Backfill script: embed every stored case's `summary` + profile text with
   `input_type="document"`, write the 1024-float vector into the existing
   `embedding` column (SQLite BLOB).
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

Decisions marked ✅ are recommended defaults; ⚖️ genuinely need the client's
(or your) call.

### 6.1 ✅ Retrieval strategy — staged (LLM-picker → embeddings)
See §5.3. The interface hides the choice; upgrade when scale demands.

### 6.2 ✅ Storage — SQLite, not a vector DB
At POC scale (≲ thousands of cases), brute-force cosine over an in-memory
numpy matrix is sub-millisecond. A vector DB (Pinecone, Qdrant, pgvector)
buys nothing yet and adds ops surface to a demo. pgvector on Postgres is the
natural production step if this graduates.

### 6.3 ⚖️ Who scores — LLM proposes, guardrails cap, human approves
Options were (a) keep deterministic scoring and only let the LLM *find*
factors, (b) let the LLM score freely, (c) the hybrid in §4.3.
**(c) recommended:** it satisfies "LLM decides its own risk factors" while
keeping a reproducible score story for insurers. Confirm the client accepts
that named per-field rules are gone.

### 6.4 ⚖️ Reflection cadence — synchronous per sign-off vs batched
Per sign-off (recommended for POC) makes the demo interactive: correct one
case, assess a similar one, watch the lesson appear. Batched (nightly) is
cheaper and produces a calmer playbook at production volume. This is one
config flag.

### 6.5 ⚖️ Playbook write access — LLM-drafted, human-owned?
Recommended: the LLM edits `playbook.md` but every edit is shown as a diff on
the review screen, and the underwriter can revert/edit. The stricter variant —
playbook edits *themselves* require approval — is more defensible to an
insurer but adds review burden. Ask the client which they want to demo.

### 6.6 ⚖️ Precedent scope — global memory vs per-insurer partitions
If this is pitched to multiple insurers, does insurer A's correction history
teach the system serving insurer B? Cross-tenant learning is a data-governance
question the client must answer before production. POC: single shared memory,
flagged in the doc.

### 6.7 ✅ Cold start / novel risks
A finding citing no precedent and no playbook rule is allowed but auto-flagged
`NOVEL` and referred. Early on most findings are novel; as memory fills,
referral rate drops — which is itself a nice "the system is learning" metric
to chart in the demo.

### 6.8 ✅ Memory hygiene
Reflection can retire rules (contradicted by newer decisions), and rules carry
supporting-case links so stale ones are traceable. Cap playbook size (~2-3k
tokens for POC); when exceeded, reflection must consolidate before adding.

### 6.9 ⚖️ Evaluation — how do we prove it's learning?
Recommend a tiny eval harness before the pitch: hold out ~10 ingested chat
cases, run assessments with memory off vs memory on, count findings that match
the human's historical decision. One number ("precedent-informed assessments
matched historical underwriter decisions X% vs Y% blind") carries the pitch.

### 6.10 ✅ Models
`claude-opus-4-8` for assess + reflect (quality-critical), `claude-haiku-4-5`
for profile pre-extraction, chat-transcript triage, and LLM-as-retriever.
Batches API for chat ingestion.

## 7. Build plan

| Phase | Deliverable | Depends on |
|---|---|---|
| 1 | `RiskFinding`/`CaseRecord` schemas + `assess.py` with empty memory (playbook stub, k=0) | — |
| 2 | `guardrails.py` (evidence check, caps, referrals) + report shows findings w/ evidence | 1 |
| 3 | `memory.py` store + LLM-as-retriever; assess now cites precedents | 1 |
| 4 | Review UI (edit + approve) + case persistence on approval | 2, 3 |
| 5 | Reflection step + playbook rendering in report | 4 |
| 6 | `ingest_chats.py` + dummy historical-chat dataset (can be synthetic for the demo) | 3 |
| 7 | Eval harness + demo script ("correct → re-assess → watch it learn") | 5, 6 |
| 8 | (optional) swap retriever to `voyage-4-lite` embeddings | 3 |

Phases 1–5 are the working self-learning loop; 6 seeds it with "their past
chats"; 7 is the proof.

## 8. Risks

- **Playbook drift / overgeneralization** — a lesson learned from 2 cases
  stated as a universal rule. Mitigated by confidence tiers, supporting-case
  links, and human-visible diffs (§6.5, §6.8).
- **Sparse chat data** — if historical transcripts are few or low-signal,
  seed the demo with synthetic-but-realistic transcripts and say so.
- **Reviewer fatigue** — the learning loop is only as good as the corrections;
  make approve-with-no-edits one click so the happy path is cheap.
- **Insurer skepticism of LLM-proposed factors** — the counter is the audit
  chain (evidence quote → precedent → playbook rule → human sign-off), which
  should be front-and-center in the report UI.
