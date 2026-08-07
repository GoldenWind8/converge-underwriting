/**
 * Stage 3: the common-drivers grouping. This is the only real logic on the
 * client side, and it is the thing that makes a multi-section view worth more
 * than 18 separate assessments - so it gets a test.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { groupDrivers } from "./DriversPanel.js";
import type { CoverSection, ProposedMetric } from "./api.js";
import type { SectionState } from "./SectionCard.js";

function section(id: string, name: string, number: number): CoverSection {
  return { id, name, number, scope: "scope note" };
}

function metric(
  name: string,
  level: string,
  drivers: string[],
): ProposedMetric {
  return {
    name,
    assessedLevel: level,
    scale: "low / high",
    reasoning: "because",
    evidence: "a field",
    drivers,
    memoryInfluenced: false,
    memoryBasis: null,
  };
}

function state(metrics: ProposedMetric[]): SectionState {
  return {
    metrics,
    memoryNote: "",
    memoryEntriesUsed: 0,
    costUsd: null,
    reviews: [],
    added: [],
    saved: null,
  };
}

const SECTIONS = [
  section("fire", "Fire", 2),
  section("business-interruption", "Business Interruption", 3),
  section("electronic-equipment", "Electronic Equipment", 11),
  section("motor", "Motor", 14),
];

test("a driver touching two or more sections is grouped; one section is not", () => {
  const groups = groupDrivers(SECTIONS, {
    fire: state([
      metric("Ignition sources", "high", [
        "hot-work-on-site",
        "no-fire-detection",
      ]),
      metric("Stock combustibility", "elevated", ["combustible-stock"]),
    ]),
    "business-interruption": state([
      metric("Single-site dependency", "high", [
        "single-premises-dependency",
        "no-fire-detection",
      ]),
    ]),
    "electronic-equipment": state([
      metric("Server room protection", "elevated", ["no-fire-detection"]),
    ]),
    motor: state([metric("Driver vetting", "weak", ["no-driver-vetting"])]),
  });

  const detection = groups.find((g) => g.driver === "no-fire-detection");
  assert.ok(detection, "the cross-cutting driver is surfaced");
  assert.equal(detection.sectionCount, 3);
  assert.deepEqual(
    detection.hits.map((h) => h.sectionName),
    ["Fire", "Business Interruption", "Electronic Equipment"],
    "hits are listed in section order, with the section named",
  );
  assert.equal(detection.hits[0].metricName, "Ignition sources");
  assert.equal(
    detection.hits[0].level,
    "high",
    "the level travels with the hit",
  );

  // Single-section drivers are noise here, so they are filtered out.
  for (const single of [
    "combustible-stock",
    "hot-work-on-site",
    "single-premises-dependency",
    "no-driver-vetting",
  ]) {
    assert.equal(
      groups.find((g) => g.driver === single),
      undefined,
      `${single} touches one section only and should not be grouped`,
    );
  }

  // Most-cross-cutting first, so the widest weakness reads at the top.
  assert.deepEqual(
    groups.map((g) => g.sectionCount),
    [...groups.map((g) => g.sectionCount)].sort((a, b) => b - a),
  );
});

test("grouping is by section, not by metric count", () => {
  // Three metrics in ONE section share a driver - that is not cross-cutting.
  const groups = groupDrivers(SECTIONS, {
    fire: state([
      metric("A", "high", ["poor-housekeeping"]),
      metric("B", "high", ["poor-housekeeping"]),
      metric("C", "high", ["poor-housekeeping"]),
    ]),
  });
  assert.deepEqual(groups, []);

  // The same driver across two sections is.
  const spread = groupDrivers(SECTIONS, {
    fire: state([metric("A", "high", ["poor-housekeeping"])]),
    motor: state([metric("B", "moderate", ["poor-housekeeping"])]),
  });
  assert.equal(spread.length, 1);
  assert.equal(spread[0].sectionCount, 2);
  assert.equal(spread[0].hits.length, 2);
});

test("unassessed sections and driverless metrics are simply absent", () => {
  assert.deepEqual(
    groupDrivers(SECTIONS, {}),
    [],
    "nothing assessed, nothing grouped",
  );
  assert.deepEqual(
    groupDrivers(SECTIONS, {
      fire: state([metric("A", "high", [])]),
      motor: state([metric("B", "high", [])]),
    }),
    [],
    "metrics with no drivers contribute nothing",
  );
});
