/**
 * Common drivers. Computed client-side from what has already been assessed -
 * no extra model call. The point: one weakness in the business surfacing under
 * several cover sections at once is what a section-by-section read hides.
 */

import type { CoverSection } from "./api.js";
import type { SectionState } from "./SectionCard.js";

interface Hit {
  sectionName: string;
  metricName: string;
  level: string;
}

export interface DriverGroup {
  driver: string;
  hits: Hit[];
  sectionCount: number;
}

export function groupDrivers(
  sections: CoverSection[],
  states: Record<string, SectionState>,
): DriverGroup[] {
  const byDriver = new Map<string, Hit[]>();

  for (const section of sections) {
    const state = states[section.id];
    if (!state) continue;
    for (const metric of state.metrics) {
      for (const driver of metric.drivers) {
        const hits = byDriver.get(driver) ?? [];
        hits.push({
          sectionName: section.name,
          metricName: metric.name,
          level: metric.assessedLevel,
        });
        byDriver.set(driver, hits);
      }
    }
  }

  return [...byDriver.entries()]
    .map(([driver, hits]) => ({
      driver,
      hits,
      sectionCount: new Set(hits.map((h) => h.sectionName)).size,
    }))
    .filter((g) => g.sectionCount >= 2)
    .sort(
      (a, b) =>
        b.sectionCount - a.sectionCount || a.driver.localeCompare(b.driver),
    );
}

interface Props {
  groups: DriverGroup[];
  assessedCount: number;
}

export default function DriversPanel({ groups, assessedCount }: Props) {
  if (assessedCount < 2) {
    return (
      <p className="hint">
        Assess at least two sections to see which weaknesses cut across them.
      </p>
    );
  }

  if (groups.length === 0) {
    return (
      <p className="hint">
        Nothing yet touches two or more of the {assessedCount} assessed
        sections.
      </p>
    );
  }

  return (
    <>
      <p className="hint">
        Each driver below is one fact about the business that surfaced under two
        or more cover sections. Computed from the assessments already run - no
        extra model call.
      </p>
      {groups.map((group) => (
        <div className="driver-group" key={group.driver}>
          <div className="driver-head">
            <span className="driver strong">{group.driver}</span>
            <span className="badge across">{group.sectionCount} sections</span>
          </div>
          <ul>
            {group.hits.map((hit, i) => (
              <li key={`${hit.sectionName}-${i}`}>
                <strong>{hit.sectionName}</strong> - {hit.metricName}{" "}
                <span className="level">{hit.level}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}
