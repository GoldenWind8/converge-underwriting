import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type Bootstrap,
  type MemoryEntry,
  type SectionNeed,
} from "./api.js";
import NeedsPanel from "./NeedsPanel.js";
import SectionCard, {
  blankSectionState,
  toCorrections,
  type SectionState,
} from "./SectionCard.js";
import DriversPanel, { groupDrivers } from "./DriversPanel.js";

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [submission, setSubmission] = useState("");
  const [submissionRef, setSubmissionRef] = useState("");

  const [needs, setNeeds] = useState<SectionNeed[] | null>(null);
  const [businessNote, setBusinessNote] = useState("");
  const [needsCost, setNeedsCost] = useState<number | null>(null);

  const [states, setStates] = useState<Record<string, SectionState>>({});
  const [memoryCounts, setMemoryCounts] = useState<Record<string, number>>({});
  const [openMemory, setOpenMemory] = useState<Record<string, MemoryEntry[]>>(
    {},
  );

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runNote, setRunNote] = useState<string | null>(null);

  useEffect(() => {
    api
      .bootstrap()
      .then(setBoot)
      .catch((e: Error) => setError(e.message));
  }, []);

  const refreshCounts = useCallback(() => {
    api
      .memoryCounts()
      .then((r) => setMemoryCounts(r.counts))
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => refreshCounts(), [refreshCounts]);

  const sections = boot?.sections ?? [];

  const required = useMemo(
    () => (needs ?? []).filter((n) => n.requirement === "required"),
    [needs],
  );

  /** Slugs already seen, so later sections reuse them instead of coining variants. */
  const knownDrivers = useMemo(() => {
    const seen = new Set<string>();
    for (const state of Object.values(states)) {
      for (const metric of state.metrics) {
        for (const d of metric.drivers) seen.add(d);
      }
    }
    return [...seen].sort();
  }, [states]);

  const driverGroups = useMemo(
    () => groupDrivers(sections, states),
    [sections, states],
  );

  function reset() {
    setNeeds(null);
    setBusinessNote("");
    setNeedsCost(null);
    setStates({});
    setOpenMemory({});
    setRunNote(null);
  }

  async function determineNeeds() {
    setBusy("needs");
    setError(null);
    setRunNote(null);
    try {
      const result = await api.needs(submission);
      setNeeds(result.needs);
      setBusinessNote(result.businessNote);
      setNeedsCost(result.costUsd);
      setStates({});
    } catch (e) {
      reset();
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  /** Assess one section. Returns its cost so the caller can total a batch. */
  async function assessOne(need: SectionNeed): Promise<number | null> {
    const result = await api.assess({
      sectionId: need.sectionId,
      submission,
      knownDrivers,
      needReason: need.reason,
      motorSubType: need.motorSubType,
    });
    setStates((prev) => ({
      ...prev,
      [need.sectionId]: blankSectionState(
        result.metrics,
        result.memoryNote,
        result.memoryEntriesUsed,
        result.costUsd,
      ),
    }));
    return result.costUsd;
  }

  async function assessSection(need: SectionNeed) {
    setBusy(need.sectionId);
    setError(null);
    try {
      await assessOne(need);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function assessAll() {
    const pending = required.filter((n) => !states[n.sectionId]);
    if (pending.length === 0) return;

    const estimate = boot?.provider.estimatedCostPerCallUsd ?? null;
    const costLine =
      estimate === null
        ? "Cost is not reported on this provider."
        : `Estimated cost: about $${(pending.length * estimate).toFixed(2)} (${pending.length} x ~$${estimate.toFixed(2)}).`;

    if (
      !window.confirm(
        `Assess ${pending.length} section${pending.length === 1 ? "" : "s"} that have not been assessed yet?\n\n${costLine}\n\nEach section is a separate model call, run one after another.`,
      )
    ) {
      return;
    }

    setError(null);
    let total = 0;
    let counted = 0;
    let done = 0;

    for (const need of pending) {
      setBusy(need.sectionId);
      setRunNote(
        `Assessing ${done + 1} of ${pending.length}: ${sectionName(need.sectionId)}...`,
      );
      try {
        const cost = await assessOne(need);
        if (cost !== null) {
          total += cost;
          counted++;
        }
        done++;
      } catch (e) {
        setError(
          `Stopped after ${done} of ${pending.length}: ${(e as Error).message}`,
        );
        break;
      }
    }

    setBusy(null);
    setRunNote(
      `Assessed ${done} section${done === 1 ? "" : "s"}.` +
        (counted > 0 ? ` Actual cost: $${total.toFixed(4)}.` : ""),
    );
  }

  async function saveSection(sectionId: string) {
    const state = states[sectionId];
    if (!state) return;

    const result = toCorrections(state);
    if ("error" in result) {
      setError(result.error);
      return;
    }

    setBusy(sectionId);
    setError(null);
    try {
      const ref =
        submissionRef.trim() || submission.split("\n")[0].slice(0, 80);
      const saved = await api.review(sectionId, ref, result.corrections);
      setMemoryCounts((prev) => ({
        ...prev,
        [sectionId]: saved.entries.length,
      }));
      setOpenMemory((prev) =>
        sectionId in prev ? { ...prev, [sectionId]: saved.entries } : prev,
      );
      setStates((prev) => ({
        ...prev,
        [sectionId]: {
          ...state,
          saved: `Saved ${result.corrections.length} correction${result.corrections.length === 1 ? "" : "s"} to ${sectionName(sectionId)} memory. Re-assess to see them applied - they affect this section only.`,
        },
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function toggleMemory(sectionId: string) {
    if (sectionId in openMemory) {
      setOpenMemory((prev) => {
        const next = { ...prev };
        delete next[sectionId];
        return next;
      });
      return;
    }
    try {
      const result = await api.memory(sectionId);
      setOpenMemory((prev) => ({ ...prev, [sectionId]: result.entries }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function clearMemory(sectionId: string) {
    setBusy(sectionId);
    try {
      const result = await api.clearMemory(sectionId);
      setMemoryCounts((prev) => ({ ...prev, [sectionId]: 0 }));
      setOpenMemory((prev) =>
        sectionId in prev ? { ...prev, [sectionId]: result.entries } : prev,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  function sectionName(sectionId: string): string {
    return sections.find((s) => s.id === sectionId)?.name ?? sectionId;
  }

  const assessedCount = Object.keys(states).length;
  const pendingCount = required.filter((n) => !states[n.sectionId]).length;

  return (
    <main>
      <header>
        <h1>Converge Underwriting - risk assessment prototype</h1>
        <p className="sub">
          A commercial submission in; which of the 18 cover sections the
          business needs; then risk metrics per section, corrected by a human
          and remembered per section. Prototype only: no pricing, no premium, no
          product.
          {boot && (
            <>
              {" "}
              Model: <code>{boot.model}</code>.
            </>
          )}
        </p>
        {boot && (
          <p className={boot.provider.id === "none" ? "warn" : "provider"}>
            <span
              className={`badge provider-${boot.provider.id}`}
              title={boot.provider.detail}
            >
              via {boot.provider.label}
            </span>{" "}
            {boot.provider.detail}
          </p>
        )}
      </header>

      {error && (
        <div className="error" role="alert">
          <strong>Error</strong>
          <pre>{error}</pre>
        </div>
      )}

      <section>
        <h2>1. Submission</h2>
        <div className="row">
          <label className="grow">
            Label for this submission (used in the memory trail)
            <input
              value={submissionRef}
              placeholder="e.g. Mabuza Bakeries"
              onChange={(e) => setSubmissionRef(e.target.value)}
            />
          </label>
        </div>

        <div className="samples">
          <span>Load a sample:</span>
          {(boot?.samples ?? []).map((s) => (
            <button
              key={s.id}
              type="button"
              className="link"
              onClick={() => {
                setSubmission(s.submission);
                setSubmissionRef(s.label);
                reset();
              }}
            >
              {s.label}
            </button>
          ))}
        </div>

        <textarea
          rows={16}
          value={submission}
          placeholder="Paste the client's proposal details here, one field per line."
          onChange={(e) => setSubmission(e.target.value)}
        />

        <div className="row">
          <button
            type="button"
            className="primary"
            disabled={busy !== null || submission.trim().length < 20}
            onClick={determineNeeds}
          >
            {busy === "needs"
              ? "Working out needs..."
              : "Determine cover needs"}
          </button>
          <span className="hint">One model call across all 18 sections.</span>
        </div>
      </section>

      <section>
        <h2>2. Cover needs</h2>
        {!needs ? (
          <p className="hint">
            Nothing yet. Load or paste a submission above and press "Determine
            cover needs".
          </p>
        ) : (
          <NeedsPanel
            sections={sections}
            motorSubTypes={boot?.motorSubTypes ?? []}
            needs={needs}
            businessNote={businessNote}
            costUsd={needsCost}
            memoryCounts={memoryCounts}
            onChange={setNeeds}
          />
        )}
      </section>

      <section>
        <h2>3. Risk assessment by section</h2>
        {!needs ? (
          <p className="hint">Determine cover needs first.</p>
        ) : required.length === 0 ? (
          <p className="hint">
            Nothing is marked required. Mark at least one section required
            above.
          </p>
        ) : (
          <>
            <div className="row">
              <button
                type="button"
                disabled={busy !== null || pendingCount === 0}
                onClick={assessAll}
              >
                Assess all required sections
                {pendingCount > 0 && ` (${pendingCount} left)`}
              </button>
              <span className="hint">
                {assessedCount} of {required.length} assessed. Sections are
                assessed one at a time, on demand - never all at once by
                surprise.
              </span>
            </div>
            {runNote && <p className="saved">{runNote}</p>}

            {required.map((need) => {
              const section = sections.find((s) => s.id === need.sectionId);
              if (!section) return null;
              const subType = boot?.motorSubTypes.find(
                (t) => t.id === need.motorSubType,
              );
              return (
                <SectionCard
                  key={need.sectionId}
                  section={section}
                  requirementReason={need.reason}
                  motorSubTypeLabel={subType?.label ?? null}
                  memoryCount={memoryCounts[need.sectionId] ?? 0}
                  state={states[need.sectionId]}
                  busy={busy === need.sectionId}
                  onAssess={() => assessSection(need)}
                  onChange={(next) =>
                    setStates((prev) => ({ ...prev, [need.sectionId]: next }))
                  }
                  onSave={() => saveSection(need.sectionId)}
                  onClearMemory={() => clearMemory(need.sectionId)}
                  memoryEntries={openMemory[need.sectionId]}
                  onToggleMemory={() => toggleMemory(need.sectionId)}
                />
              );
            })}
          </>
        )}
      </section>

      <section>
        <h2>4. Common drivers</h2>
        <DriversPanel groups={driverGroups} assessedCount={assessedCount} />
      </section>
    </main>
  );
}
