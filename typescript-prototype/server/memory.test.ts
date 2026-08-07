/**
 * The things that must hold for this prototype to be trustworthy:
 *   1. corrections survive a restart, and are scoped per cover section
 *   2. corrections reach their own section's prompt and no other's
 *   3. needs determination validates against the 18 sections
 *   4. a malformed model response surfaces as a readable error
 * plus sensitivity checks on the edges of each.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createMemoryStore, parseCorrections } from "./memory.js";
import { ProposalParseError, parseNeeds, parseProposal } from "./parse.js";
import { buildNeedsSystemPrompt, buildSectionSystemPrompt } from "./prompt.js";
import { COVER_SECTIONS, findSection } from "./domain.js";
import { extractJsonObject } from "./provider-cli.js";

async function withTempStore<T>(fn: (file: string) => Promise<T>): Promise<T> {
  const dir = await mkdtemp(path.join(tmpdir(), "cu-proto-"));
  try {
    return await fn(path.join(dir, "nested", "memory.json"));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("the 18 cover sections are present, unique and ordered", () => {
  assert.equal(COVER_SECTIONS.length, 18);
  assert.deepEqual(
    COVER_SECTIONS.map((s) => s.number),
    Array.from({ length: 18 }, (_, i) => i + 1),
    "numbers run 1-18 in order, matching the needs analysis",
  );
  assert.equal(
    new Set(COVER_SECTIONS.map((s) => s.id)).size,
    18,
    "ids are unique",
  );
  for (const section of COVER_SECTIONS) {
    assert.ok(section.scope.length > 20, `${section.id} has a scope note`);
  }
});

test("memory: corrections persist per section across a fresh store instance", async () => {
  await withTempStore(async (file) => {
    const first = createMemoryStore(file);

    // Nothing on disk yet - a missing file reads as empty, not an error.
    assert.deepEqual(await first.read("theft"), []);

    await first.append("theft", "Mabuza Bakeries", [
      {
        action: "edited",
        metricName: "Perimeter and access control",
        assessedLevel: "high",
        proposedName: "Physical security",
        proposedLevel: "moderate",
        note: "Palisade plus alarm with no CCTV is high for a stock-holding site.",
      },
      {
        action: "rejected",
        metricName: "Stock value concentration",
        assessedLevel: null,
        proposedLevel: "moderate",
        note: "Belongs under Fire, not Theft.",
      },
    ]);
    await first.append("motor", "Mabuza Bakeries", [
      { action: "added", metricName: "Driver vetting", assessedLevel: "weak" },
    ]);

    // A brand-new store object, as if the process had restarted.
    const restarted = createMemoryStore(file);
    const theft = await restarted.read("theft");
    const motor = await restarted.read("motor");

    assert.equal(theft.length, 2, "theft corrections survive the restart");
    assert.equal(motor.length, 1, "motor memory is scoped separately");
    assert.deepEqual(
      theft.map((e) => e.action),
      ["edited", "rejected"],
      "order is preserved, oldest first",
    );

    const edited = theft[0];
    assert.equal(edited.assessedLevel, "high");
    assert.equal(
      edited.proposedLevel,
      "moderate",
      "what the model proposed is kept too",
    );
    assert.equal(edited.submissionRef, "Mabuza Bakeries");
    assert.ok(
      edited.id && edited.at,
      "each entry is identifiable and timestamped",
    );

    // A later review appends rather than replacing.
    await restarted.append("theft", "Kaap Timber", [
      {
        action: "accepted",
        metricName: "Lock and key control",
        assessedLevel: "adequate",
      },
    ]);
    assert.equal((await createMemoryStore(file).read("theft")).length, 3);

    // Clearing one section leaves the others alone.
    await restarted.clear("theft");
    assert.deepEqual(await restarted.read("theft"), []);
    assert.equal((await restarted.read("motor")).length, 1);

    // A section never written to is simply empty.
    assert.deepEqual(await restarted.read("glass"), []);
  });
});

test("memory reaches its own section's prompt and no other", async () => {
  await withTempStore(async (file) => {
    const store = createMemoryStore(file);
    const theft = findSection("theft")!;
    const motor = findSection("motor")!;

    const cold = buildSectionSystemPrompt({
      section: theft,
      memory: [],
      knownDrivers: [],
    });
    assert.match(cold, /none yet/, "an unassessed section says so explicitly");
    assert.match(
      cold,
      /8\. Theft/,
      "the prompt names the section under assessment",
    );
    assert.match(
      cold,
      /Never produce a premium/,
      "the no-pricing boundary is always present",
    );

    const entries = await store.append("theft", "Mabuza Bakeries", [
      {
        action: "edited",
        metricName: "Perimeter and access control",
        assessedLevel: "high",
        proposedLevel: "moderate",
        note: "No CCTV on a stock-holding site is high.",
      },
    ]);

    const warm = buildSectionSystemPrompt({
      section: theft,
      memory: entries,
      knownDrivers: ["no-cctv", "combustible-stock"],
    });
    assert.match(warm, /\[edited\] Perimeter and access control/);
    assert.match(
      warm,
      /"moderate"/,
      "the prompt shows what the model had proposed",
    );
    assert.match(warm, /"high"/, "and what the underwriter corrected it to");
    assert.match(warm, /No CCTV on a stock-holding site is high\./);
    assert.match(warm, /standing instructions/, "memory is authoritative");
    assert.match(
      warm,
      /Already used on other sections/,
      "known slugs are offered for reuse",
    );
    assert.match(warm, /no-cctv/);

    // The correction must not leak into a different section's prompt.
    const otherSection = buildSectionSystemPrompt({
      section: motor,
      memory: await store.read("motor"),
      knownDrivers: [],
    });
    assert.doesNotMatch(otherSection, /Perimeter and access control/);
    assert.match(otherSection, /none yet/);
  });
});

test("motor sub-type changes what the section prompt asks for", () => {
  const motor = findSection("motor")!;
  const comprehensive = buildSectionSystemPrompt({
    section: motor,
    memory: [],
    knownDrivers: [],
    motorSubType: "comprehensive",
  });
  const thirdParty = buildSectionSystemPrompt({
    section: motor,
    memory: [],
    knownDrivers: [],
    motorSubType: "third-party-only",
  });

  assert.match(comprehensive, /Comprehensive/);
  assert.match(thirdParty, /Third Party only/);
  assert.match(
    thirdParty,
    /own-damage exposure is not worth assessing/,
    "the sub-type steers what is in scope",
  );
});

test("the needs prompt covers every section and pushes back on blanket answers", () => {
  const prompt = buildNeedsSystemPrompt();
  for (const section of COVER_SECTIONS) {
    assert.match(
      prompt,
      new RegExp(`- ${section.id} \\(`),
      `${section.id} appears in the needs prompt`,
    );
  }
  assert.match(prompt, /not-applicable/);
  assert.match(
    prompt,
    /same as no analysis/,
    "it is told not to mark everything required",
  );
  assert.match(prompt, /Never produce a premium/);
});

test("needs parsing validates section ids and fills gaps rather than dropping them", () => {
  const full = parseNeeds(
    JSON.stringify({
      businessNote: "An industrial bakery.",
      needs: COVER_SECTIONS.map((s) => ({
        sectionId: s.id,
        requirement: s.id === "motor-traders" ? "not-applicable" : "required",
        reason: "because of a fact in the submission",
        motorSubType: s.id === "motor" ? "comprehensive" : "",
      })),
    }),
  );
  assert.equal(full.needs.length, 18);
  assert.equal(
    full.needs.find((n) => n.sectionId === "motor")?.motorSubType,
    "comprehensive",
  );
  assert.equal(
    full.needs.find((n) => n.sectionId === "fire")?.motorSubType,
    null,
    "a sub-type on a non-motor section is discarded",
  );

  // A short response is padded to all 18, with the gap stated rather than hidden.
  const partial = parseNeeds(
    JSON.stringify({
      businessNote: "",
      needs: [
        {
          sectionId: "fire",
          requirement: "required",
          reason: "holds stock",
          motorSubType: "",
        },
      ],
    }),
  );
  assert.equal(partial.needs.length, 18);
  const gap = partial.needs.find((n) => n.sectionId === "glass")!;
  assert.equal(gap.requirement, "not-applicable");
  assert.match(gap.reason, /did not return an entry/);
  assert.deepEqual(
    partial.needs.map((n) => n.sectionId),
    COVER_SECTIONS.map((s) => s.id),
    "output is always in section order",
  );

  const bad: Array<[string, RegExp]> = [
    ['{"needs":[]}', /returned no needs/],
    ['{"needs":"nope"}', /`needs` is missing/],
    [
      JSON.stringify({
        needs: [{ sectionId: "cyber", requirement: "required", reason: "x" }],
      }),
      /is not one of the cover sections/,
    ],
    [
      JSON.stringify({
        needs: [{ sectionId: "fire", requirement: "maybe", reason: "x" }],
      }),
      /requirement must be one of/,
    ],
    [
      JSON.stringify({
        needs: [{ sectionId: "fire", requirement: "required", reason: "  " }],
      }),
      /reason must be a non-empty string/,
    ],
    [
      JSON.stringify({
        needs: [
          { sectionId: "fire", requirement: "required", reason: "a" },
          { sectionId: "fire", requirement: "consider", reason: "b" },
        ],
      }),
      /appears more than once/,
    ],
  ];
  for (const [input, expected] of bad) {
    assert.throws(
      () => parseNeeds(input),
      expected,
      `should reject ${input.slice(0, 50)}`,
    );
  }
});

test("corrections validation rejects malformed input from the UI", () => {
  assert.throws(() => parseCorrections("nope"), /must be an array/);
  assert.throws(() => parseCorrections([]), /must not be empty/);
  assert.throws(
    () =>
      parseCorrections([
        { action: "maybe", metricName: "X", assessedLevel: "low" },
      ]),
    /action must be one of/,
  );
  assert.throws(
    () =>
      parseCorrections([
        { action: "accepted", metricName: "  ", assessedLevel: "low" },
      ]),
    /metricName/,
  );
  assert.throws(
    () => parseCorrections([{ action: "added", metricName: "X" }]),
    /assessedLevel is required/,
    "an added metric needs a level",
  );

  // A rejected metric legitimately has no level, and blank notes become null.
  assert.deepEqual(
    parseCorrections([
      { action: "rejected", metricName: " Stock value ", note: "   " },
    ]),
    [
      {
        action: "rejected",
        metricName: "Stock value",
        assessedLevel: null,
        proposedName: null,
        proposedLevel: null,
        note: null,
      },
    ],
  );
});

const goodMetric = {
  name: "Perimeter and access control",
  assessedLevel: "elevated",
  scale: "low / elevated / high",
  reasoning: "Palisade fencing and an alarm, but no CCTV.",
  evidence:
    "Security: Palisade fencing, alarm linked to armed response, no CCTV",
  drivers: ["no-cctv", "perimeter-security-only"],
  memoryInfluenced: false,
  memoryBasis: "",
};

test("proposal parsing normalises drivers so they group reliably", () => {
  const proposal = parseProposal(
    JSON.stringify({
      memoryNote: "No memory to draw on.",
      metrics: [
        goodMetric,
        {
          ...goodMetric,
          name: " Stock exposure ",
          // The same slug written four sloppy ways must collapse to one.
          drivers: ["No CCTV", "no_cctv", "  no-cctv  ", "NO--CCTV!"],
          memoryInfluenced: true,
          memoryBasis: " correction 1 moved this up ",
        },
      ],
    }),
  );

  assert.equal(proposal.metrics.length, 2);
  assert.deepEqual(proposal.metrics[0].drivers, [
    "no-cctv",
    "perimeter-security-only",
  ]);
  assert.deepEqual(
    proposal.metrics[1].drivers,
    ["no-cctv"],
    "case, spacing, underscores and punctuation all normalise to one slug",
  );
  assert.equal(
    proposal.metrics[0].memoryBasis,
    null,
    "no influence means no basis",
  );
  assert.equal(proposal.metrics[1].name, "Stock exposure");
  assert.equal(proposal.metrics[1].memoryBasis, "correction 1 moved this up");

  // Drivers are optional on the wire; a metric without them is still valid.
  const noDrivers = parseProposal(
    JSON.stringify({ metrics: [{ ...goodMetric, drivers: undefined }] }),
  );
  assert.deepEqual(noDrivers.metrics[0].drivers, []);
});

test("proposal parsing surfaces every malformed shape as a readable error", () => {
  const cases: Array<[string, RegExp]> = [
    ["", /returned no text/],
    ["not json at all", /not valid JSON/],
    ["[1,2,3]", /JSON object at the top level/],
    ['{"memoryNote":"x"}', /`metrics` is missing/],
    ['{"metrics":[]}', /proposed no metrics/],
    ['{"metrics":["a string"]}', /metrics\[0\] is not an object/],
    [
      JSON.stringify({ metrics: [{ ...goodMetric, evidence: "" }] }),
      /evidence must be a non-empty string/,
    ],
    [
      JSON.stringify({ metrics: [{ ...goodMetric, assessedLevel: 3 }] }),
      /assessedLevel must be a non-empty string/,
    ],
    [
      JSON.stringify({ metrics: [{ ...goodMetric, memoryInfluenced: "yes" }] }),
      /memoryInfluenced must be a boolean/,
    ],
    [
      JSON.stringify({ metrics: [{ ...goodMetric, drivers: "no-cctv" }] }),
      /drivers must be an array/,
    ],
    [
      JSON.stringify({ metrics: [{ ...goodMetric, drivers: [7] }] }),
      /drivers must contain only strings/,
    ],
    [
      JSON.stringify({
        metrics: [{ ...goodMetric, memoryInfluenced: true, memoryBasis: "" }],
      }),
      /claims memory influence but gives no memoryBasis/,
    ],
  ];

  for (const [input, expected] of cases) {
    assert.throws(
      () => parseProposal(input),
      (err: unknown) => {
        assert.ok(
          err instanceof ProposalParseError,
          `expected ProposalParseError for ${input}`,
        );
        assert.match(err.message, expected);
        return true;
      },
      `input ${JSON.stringify(input).slice(0, 60)} should be rejected`,
    );
  }
});

test("CLI provider: JSON is extracted from fenced or prose-wrapped output", () => {
  const json = JSON.stringify({ memoryNote: "", metrics: [goodMetric] });

  const variants = [
    json,
    `\`\`\`json\n${json}\n\`\`\``,
    `\`\`\`\n${json}\n\`\`\``,
    `Here is the assessment:\n\n${json}\n\nLet me know if you want more.`,
    `  \n${json}\n  `,
  ];

  for (const variant of variants) {
    const proposal = parseProposal(extractJsonObject(variant));
    assert.equal(
      proposal.metrics[0].name,
      "Perimeter and access control",
      `failed on: ${variant.slice(0, 40)}`,
    );
  }

  // Braces inside string values must not end the object early.
  const tricky = JSON.stringify({
    memoryNote: "note with } and { braces",
    metrics: [{ ...goodMetric, evidence: 'Security: "{unclear}"' }],
  });
  assert.equal(
    parseProposal(extractJsonObject(`prose ${tricky} more prose`)).metrics[0]
      .evidence,
    'Security: "{unclear}"',
  );

  // The needs response goes through the same extraction.
  const needsJson = JSON.stringify({
    businessNote: "A bakery.",
    needs: [
      {
        sectionId: "fire",
        requirement: "required",
        reason: "holds stock",
        motorSubType: "",
      },
    ],
  });
  assert.equal(
    parseNeeds(extractJsonObject(`\`\`\`json\n${needsJson}\n\`\`\``))
      .businessNote,
    "A bakery.",
  );

  // Genuinely malformed output must still fail, not be coerced into passing.
  assert.throws(
    () => parseProposal(extractJsonObject("I cannot assess this.")),
    ProposalParseError,
  );
  assert.throws(
    () => parseProposal(extractJsonObject("```json\n{oops\n```")),
    ProposalParseError,
  );
});
