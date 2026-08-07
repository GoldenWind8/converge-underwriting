import { useState } from "react";
import type {
  Correction,
  CoverSection,
  MemoryEntry,
  ProposedMetric,
} from "./api.js";

export type Status = "pending" | "accepted" | "edited" | "rejected";

export interface Review {
  status: Status;
  name: string;
  level: string;
  note: string;
}

export interface AddedMetric {
  name: string;
  level: string;
  note: string;
}

/** Everything the UI holds about one section's assessment. */
export interface SectionState {
  metrics: ProposedMetric[];
  memoryNote: string;
  memoryEntriesUsed: number;
  costUsd: number | null;
  reviews: Review[];
  added: AddedMetric[];
  saved: string | null;
}

export function blankSectionState(
  metrics: ProposedMetric[],
  memoryNote: string,
  memoryEntriesUsed: number,
  costUsd: number | null,
): SectionState {
  return {
    metrics,
    memoryNote,
    memoryEntriesUsed,
    costUsd,
    reviews: metrics.map((m) => ({
      status: "pending",
      name: m.name,
      level: m.assessedLevel,
      note: "",
    })),
    added: [],
    saved: null,
  };
}

/** Turn the human's review state into the corrections the API remembers. */
export function toCorrections(
  state: SectionState,
): { corrections: Correction[] } | { error: string } {
  const corrections: Correction[] = [];

  state.metrics.forEach((metric, i) => {
    const review = state.reviews[i];
    if (!review || review.status === "pending") return;
    corrections.push({
      action: review.status,
      metricName:
        review.status === "rejected" ? metric.name : review.name.trim(),
      assessedLevel: review.status === "rejected" ? null : review.level.trim(),
      proposedName: metric.name,
      proposedLevel: metric.assessedLevel,
      note: review.note.trim() || null,
    });
  });

  for (const m of state.added) {
    if (!m.name.trim() || !m.level.trim()) {
      return { error: "Every added metric needs both a name and a level." };
    }
    corrections.push({
      action: "added",
      metricName: m.name.trim(),
      assessedLevel: m.level.trim(),
      note: m.note.trim() || null,
    });
  }

  if (corrections.length === 0) {
    return {
      error:
        "Nothing to save - accept, edit, reject or add at least one metric.",
    };
  }
  return { corrections };
}

interface Props {
  section: CoverSection;
  requirementReason: string;
  motorSubTypeLabel: string | null;
  memoryCount: number;
  state: SectionState | undefined;
  busy: boolean;
  onAssess: () => void;
  onChange: (next: SectionState) => void;
  onSave: () => void;
  onClearMemory: () => void;
  memoryEntries: MemoryEntry[] | undefined;
  onToggleMemory: () => void;
}

export default function SectionCard({
  section,
  requirementReason,
  motorSubTypeLabel,
  memoryCount,
  state,
  busy,
  onAssess,
  onChange,
  onSave,
  onClearMemory,
  memoryEntries,
  onToggleMemory,
}: Props) {
  const [open, setOpen] = useState(false);
  const influenced =
    state?.metrics.filter((m) => m.memoryInfluenced).length ?? 0;
  const decided =
    state?.reviews.filter((r) => r.status !== "pending").length ?? 0;

  const patchReview = (i: number, patch: Partial<Review>) => {
    if (!state) return;
    onChange({
      ...state,
      reviews: state.reviews.map((r, j) => (j === i ? { ...r, ...patch } : r)),
      saved: null,
    });
  };

  const patchAdded = (i: number, patch: Partial<AddedMetric>) => {
    if (!state) return;
    onChange({
      ...state,
      added: state.added.map((m, j) => (j === i ? { ...m, ...patch } : m)),
      saved: null,
    });
  };

  return (
    <article className="section-card">
      <header className="section-head">
        <button
          type="button"
          className="disclosure"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          {open ? "▾" : "▸"} {section.number}. {section.name}
        </button>
        {motorSubTypeLabel && (
          <span className="badge subtype">{motorSubTypeLabel}</span>
        )}
        {memoryCount > 0 && (
          <span
            className="badge memory"
            title="Remembered corrections for this section"
          >
            {memoryCount} in memory
          </span>
        )}
        {state && (
          <span className="badge assessed">
            {state.metrics.length} metric{state.metrics.length === 1 ? "" : "s"}
            {influenced > 0 && `, ${influenced} from memory`}
          </span>
        )}
        <span className="spacer" />
        <button type="button" onClick={onAssess} disabled={busy}>
          {busy ? "Assessing..." : state ? "Re-assess" : "Assess"}
        </button>
      </header>

      <p className="reason">{requirementReason}</p>

      {open && (
        <div className="section-body">
          {!state ? (
            <p className="hint">
              Not assessed yet. One model call, on demand - nothing is assessed
              until you ask.
            </p>
          ) : (
            <>
              <p className="memory-note">
                <span className="badge memory">memory</span>{" "}
                {state.memoryEntriesUsed} correction
                {state.memoryEntriesUsed === 1 ? "" : "s"} in play, {influenced}{" "}
                of {state.metrics.length} metric
                {state.metrics.length === 1 ? "" : "s"} influenced.{" "}
                {state.memoryNote}
              </p>

              {state.metrics.map((metric, i) => {
                const review = state.reviews[i];
                return (
                  <div
                    key={`${metric.name}-${i}`}
                    className={`metric ${review?.status ?? "pending"}`}
                  >
                    <div className="metric-head">
                      <h4>{metric.name}</h4>
                      <span className="level">{metric.assessedLevel}</span>
                      <span
                        className={`badge ${metric.memoryInfluenced ? "memory" : "fresh"}`}
                        title={
                          metric.memoryBasis ??
                          "reasoned from this submission alone"
                        }
                      >
                        {metric.memoryInfluenced
                          ? "from memory"
                          : "fresh reasoning"}
                      </span>
                    </div>

                    {metric.scale && (
                      <p className="scale">Scale: {metric.scale}</p>
                    )}
                    <p>{metric.reasoning}</p>
                    <blockquote>{metric.evidence}</blockquote>

                    {metric.drivers.length > 0 && (
                      <p className="drivers">
                        {metric.drivers.map((d) => (
                          <span key={d} className="driver">
                            {d}
                          </span>
                        ))}
                      </p>
                    )}

                    {metric.memoryInfluenced && metric.memoryBasis && (
                      <p className="basis">
                        <strong>Memory applied:</strong> {metric.memoryBasis}
                      </p>
                    )}

                    <div className="actions">
                      {(["accepted", "edited", "rejected"] as const).map(
                        (status) => (
                          <button
                            key={status}
                            type="button"
                            className={
                              review?.status === status ? "chosen" : ""
                            }
                            onClick={() =>
                              patchReview(i, {
                                status:
                                  review?.status === status
                                    ? "pending"
                                    : status,
                              })
                            }
                          >
                            {status === "accepted"
                              ? "Accept"
                              : status === "edited"
                                ? "Edit"
                                : "Reject"}
                          </button>
                        ),
                      )}
                    </div>

                    {review?.status === "edited" && (
                      <div className="edit">
                        <label>
                          Name
                          <input
                            value={review.name}
                            onChange={(e) =>
                              patchReview(i, { name: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Level
                          <input
                            value={review.level}
                            onChange={(e) =>
                              patchReview(i, { level: e.target.value })
                            }
                          />
                        </label>
                      </div>
                    )}

                    {review && review.status !== "pending" && (
                      <label className="note">
                        Why (remembered verbatim, so it shapes the next
                        assessment of this section)
                        <input
                          value={review.note}
                          placeholder={
                            review.status === "rejected"
                              ? "e.g. not material under this section"
                              : "e.g. read this evidence harder next time"
                          }
                          onChange={(e) =>
                            patchReview(i, { note: e.target.value })
                          }
                        />
                      </label>
                    )}
                  </div>
                );
              })}

              <h5 className="added-head">Metrics the model missed</h5>
              {state.added.map((m, i) => (
                <div className="edit added" key={i}>
                  <label>
                    Name
                    <input
                      value={m.name}
                      onChange={(e) => patchAdded(i, { name: e.target.value })}
                    />
                  </label>
                  <label>
                    Level
                    <input
                      value={m.level}
                      onChange={(e) => patchAdded(i, { level: e.target.value })}
                    />
                  </label>
                  <label className="grow">
                    Why
                    <input
                      value={m.note}
                      onChange={(e) => patchAdded(i, { note: e.target.value })}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() =>
                      onChange({
                        ...state,
                        added: state.added.filter((_, j) => j !== i),
                      })
                    }
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  onChange({
                    ...state,
                    added: [...state.added, { name: "", level: "", note: "" }],
                  })
                }
              >
                + Add a metric
              </button>

              <div className="row save">
                <button
                  type="button"
                  className="primary"
                  disabled={busy}
                  onClick={onSave}
                >
                  Save corrections to {section.name} memory
                </button>
                <span className="hint">
                  {decided} of {state.metrics.length} reviewed
                  {state.added.length > 0 && `, ${state.added.length} added`}
                  {state.costUsd !== null &&
                    ` - this assessment cost $${state.costUsd.toFixed(4)}`}
                </span>
              </div>
              {state.saved && <p className="saved">{state.saved}</p>}
            </>
          )}

          <div className="row memory-controls">
            <button type="button" onClick={onToggleMemory}>
              {memoryEntries ? "Hide" : "Show"} this section's memory (
              {memoryCount})
            </button>
            {memoryCount > 0 && (
              <button type="button" onClick={onClearMemory} disabled={busy}>
                Clear it
              </button>
            )}
          </div>

          {memoryEntries && (
            <ol className="memory-list">
              {memoryEntries.length === 0 && (
                <li className="hint">Nothing remembered for this section.</li>
              )}
              {memoryEntries.map((e) => (
                <li key={e.id}>
                  <span className={`badge action-${e.action}`}>{e.action}</span>{" "}
                  <strong>{e.metricName}</strong>
                  {e.assessedLevel && (
                    <>
                      {" "}
                      at <em>{e.assessedLevel}</em>
                    </>
                  )}
                  {e.action === "edited" && e.proposedLevel && (
                    <>
                      {" "}
                      (model had proposed <em>{e.proposedLevel}</em>)
                    </>
                  )}
                  {e.note && <div className="note-line">{e.note}</div>}
                  <div className="meta">
                    {e.submissionRef} - {new Date(e.at).toLocaleString()}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </article>
  );
}
