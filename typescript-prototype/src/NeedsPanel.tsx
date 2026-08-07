/**
 * Stage 1: which cover sections does this business need? The model proposes,
 * the human confirms or overrides, and the confirmed set drives stage 2.
 */

import type {
  CoverSection,
  MotorSubType,
  Requirement,
  SectionNeed,
} from "./api.js";

const MOTOR_SECTION_ID = "motor";

const LABELS: Record<Requirement, string> = {
  required: "Required",
  consider: "Consider",
  "not-applicable": "N/A",
};

interface Props {
  sections: CoverSection[];
  motorSubTypes: MotorSubType[];
  needs: SectionNeed[];
  businessNote: string;
  costUsd: number | null;
  memoryCounts: Record<string, number>;
  onChange: (next: SectionNeed[]) => void;
}

export default function NeedsPanel({
  sections,
  motorSubTypes,
  needs,
  businessNote,
  costUsd,
  memoryCounts,
  onChange,
}: Props) {
  const byId = new Map(needs.map((n) => [n.sectionId, n]));
  const counts = {
    required: needs.filter((n) => n.requirement === "required").length,
    consider: needs.filter((n) => n.requirement === "consider").length,
    "not-applicable": needs.filter((n) => n.requirement === "not-applicable")
      .length,
  };

  const patch = (sectionId: string, changes: Partial<SectionNeed>) => {
    onChange(
      needs.map((n) => (n.sectionId === sectionId ? { ...n, ...changes } : n)),
    );
  };

  return (
    <>
      <p className="memory-note">
        {businessNote}{" "}
        <strong>
          {counts.required} required, {counts.consider} to consider,{" "}
          {counts["not-applicable"]} not applicable.
        </strong>
        {costUsd !== null && (
          <> This needs analysis cost ${costUsd.toFixed(4)}.</>
        )}
      </p>
      <p className="hint">
        Override anything the model got wrong. What you leave as{" "}
        <em>Required</em> is what gets assessed.
      </p>

      <table className="needs">
        <tbody>
          {sections.map((section) => {
            const need = byId.get(section.id);
            if (!need) return null;
            const memoryCount = memoryCounts[section.id] ?? 0;
            return (
              <tr key={section.id} className={`need ${need.requirement}`}>
                <td className="need-name">
                  <span title={section.scope}>
                    {section.number}. {section.name}
                  </span>
                  {memoryCount > 0 && (
                    <span className="badge memory">
                      {memoryCount} in memory
                    </span>
                  )}
                  {section.id === MOTOR_SECTION_ID &&
                    need.requirement !== "not-applicable" && (
                      <select
                        value={need.motorSubType ?? ""}
                        onChange={(e) =>
                          patch(section.id, {
                            motorSubType: e.target.value || null,
                          })
                        }
                      >
                        <option value="">(choose sub-type)</option>
                        {motorSubTypes.map((t) => (
                          <option key={t.id} value={t.id} title={t.note}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                    )}
                </td>
                <td className="need-reason">{need.reason}</td>
                <td className="need-controls">
                  {(
                    ["required", "consider", "not-applicable"] as Requirement[]
                  ).map((req) => (
                    <button
                      key={req}
                      type="button"
                      className={need.requirement === req ? "chosen" : ""}
                      onClick={() => patch(section.id, { requirement: req })}
                    >
                      {LABELS[req]}
                    </button>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
