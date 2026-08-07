/**
 * The prompts. These are the substance of the prototype - everything else is
 * plumbing around them. Iterate here.
 *
 * There are two, deliberately separate:
 *   1. NEEDS - which cover sections this business actually needs. Getting this
 *      right is most of the value; it is the needs analysis itself.
 *   2. SECTION - risk metrics within one section, anchored in the client's own
 *      words, shaped by accumulated underwriter corrections for that section.
 */

import type { CoverSection, MemoryEntry } from "./domain.js";
import {
  COVER_SECTIONS,
  DRIVER_VOCABULARY,
  MOTOR_SUB_TYPES,
} from "./domain.js";

const NO_PRICING = `Hard boundary: you are assessing risk, not pricing it. Never produce a premium, a rand or currency amount, a rate, a sum insured, a loss ratio, a claims frequency or severity figure, a probability, or any calculation. No formulas, no arithmetic. If you feel the pull to quantify, express the judgement on your own qualitative scale instead.`;

/* ================================================================== *
 * Stage 1: needs determination
 * ================================================================== */

export const NEEDS_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["businessNote", "needs"],
  properties: {
    businessNote: {
      type: "string",
      description:
        "One sentence on what this business is and does, as you read it from the submission.",
    },
    needs: {
      type: "array",
      description:
        "Exactly one entry per cover section listed in the system prompt, in that order.",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["sectionId", "requirement", "reason", "motorSubType"],
        properties: {
          sectionId: {
            type: "string",
            description:
              "The section id exactly as given in the system prompt.",
          },
          requirement: {
            type: "string",
            enum: ["required", "consider", "not-applicable"],
          },
          reason: {
            type: "string",
            description:
              "One line, grounded in the submission. Name the fact that decides it.",
          },
          motorSubType: {
            type: "string",
            description:
              "Only for the motor section, and only when it is required or worth considering: one of the sub-type ids given in the system prompt. Empty string otherwise.",
          },
        },
      },
    },
  },
} as const;

export function buildNeedsSystemPrompt(): string {
  return [
    `You are the needs-analysis engine inside Converge Underwriting, a tool used by South African short-term insurance underwriters and brokers. A commercial submission has come in. Before anyone assesses risk, someone has to work out which cover sections this business actually needs.`,
    ``,
    `Go through every section below and place it in one of three buckets:`,
    `- required: the submission shows an exposure this section is for. The business would be exposed without it.`,
    `- consider: plausibly relevant, but the submission does not settle it - the exposure may be small, or a fact you would need is missing. Say which fact.`,
    `- not-applicable: the submission positively rules it out. Not "probably fine" - genuinely no exposure, or someone else carries it.`,
    ``,
    `Decide from the submission, not from what a business of this type usually buys. Concretely: a business with no vehicles does not need Motor; a tenant whose landlord insures the structure does not need Buildings Combined; a business that handles no cash does not need Money; a business that does not repair or sell vehicles for a living does not need Motor Traders. Where the submission is silent on something material, that is "consider" with the missing fact named - not "required" on a guess, and not "not-applicable" on an assumption.`,
    ``,
    `Be willing to mark sections not-applicable. An analysis that marks everything required is the same as no analysis, and it puts the client on cover they cannot claim under.`,
    ``,
    `Give exactly one entry per section, using the section id verbatim, in the order listed.`,
    ``,
    NO_PRICING,
    ``,
    `The cover sections:`,
    ``,
    ...COVER_SECTIONS.map(
      (s) => `- ${s.id} (${s.number}. ${s.name}): ${s.scope}`,
    ),
    ``,
    `Motor sub-types. If the motor section is required or worth considering, choose the sub-type that fits what the submission says about the vehicles and how the business depends on them, and justify that choice in the reason. Use the id:`,
    ...MOTOR_SUB_TYPES.map((t) => `- ${t.id} (${t.label}): ${t.note}`),
  ].join("\n");
}

export function buildNeedsUserPrompt(submission: string): string {
  return [
    `Here is the commercial submission. Work out which cover sections this business needs.`,
    ``,
    `<submission>`,
    submission.trim(),
    `</submission>`,
  ].join("\n");
}

/* ================================================================== *
 * Stage 2: per-section risk assessment
 * ================================================================== */

export const PROPOSAL_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["memoryNote", "metrics"],
  properties: {
    memoryNote: {
      type: "string",
      description:
        "One sentence on how the remembered underwriter corrections shaped this proposal. If there were none, say so.",
    },
    metrics: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "name",
          "assessedLevel",
          "scale",
          "reasoning",
          "evidence",
          "drivers",
          "memoryInfluenced",
          "memoryBasis",
        ],
        properties: {
          name: {
            type: "string",
            description: "What is being assessed, as a short noun phrase.",
          },
          assessedLevel: {
            type: "string",
            description:
              "The assessed level on whatever scale you chose for this metric.",
          },
          scale: {
            type: "string",
            description:
              "The scale this level sits on, stated compactly, e.g. 'low / moderate / elevated / high' or 'A-E, A best'.",
          },
          reasoning: {
            type: "string",
            description: "One or two sentences. Why this level.",
          },
          evidence: {
            type: "string",
            description:
              "The specific part of the submission that drove this. Quote it verbatim, or name the field and give its value.",
          },
          drivers: {
            type: "array",
            description:
              "One to three slugs naming the underlying facts about the business that drive this metric. Reuse the vocabulary given in the system prompt.",
            items: { type: "string" },
          },
          memoryInfluenced: {
            type: "boolean",
            description:
              "True only if a remembered underwriter correction changed this metric's presence, name, level or framing.",
          },
          memoryBasis: {
            type: "string",
            description:
              "When memoryInfluenced is true, name the correction(s) you applied and what they changed. When false, use an empty string.",
          },
        },
      },
    },
  },
} as const;

export function buildSectionSystemPrompt(args: {
  section: CoverSection;
  memory: MemoryEntry[];
  /** Slugs already used on other sections of this same submission. */
  knownDrivers: string[];
  /** Requirement reason from stage 1, so the assessment knows why it is here. */
  needReason?: string | null;
  /** Chosen motor sub-type, when assessing the motor section. */
  motorSubType?: string | null;
}): string {
  const { section, memory, knownDrivers, needReason, motorSubType } = args;
  const subType = MOTOR_SUB_TYPES.find((t) => t.id === motorSubType);

  const lines = [
    `You are the risk-assessment engine inside Converge Underwriting, a tool used by South African short-term insurance underwriters. An underwriter has a commercial submission in front of them and wants your read on one cover section of it before they form their own view.`,
    ``,
    `Cover section under assessment: ${section.number}. ${section.name}`,
    `What this section covers: ${section.scope}`,
  ];

  if (needReason) {
    lines.push(`Why this section is in scope for this client: ${needReason}`);
  }
  if (subType) {
    lines.push(
      `Motor sub-type selected: ${subType.label}. ${subType.note} Assess only what this sub-type actually exposes the insurer to - own-damage exposure is not worth assessing under third-party-only cover.`,
    );
  }

  lines.push(
    ``,
    `Assess this section and only this section. The other sections are being assessed separately, so do not range across the whole submission: a fact matters here only insofar as it bears on ${section.name}. Where the same underlying weakness also affects other sections, name it in the drivers field and leave those sections to their own assessment.`,
    ``,
    `Propose the risk metrics that matter for this section - typically three to six. For each metric:`,
    `- Name what is being assessed.`,
    `- Assess a level. Choose whatever scale genuinely fits that metric; do not force everything onto one house scale, and state the scale you used. Different metrics may sit on different scales.`,
    `- Explain your reasoning in one or two sentences.`,
    `- Anchor it in the submission. Quote the client's own words verbatim, or name the field and give its value. This anchoring is not optional: a metric an underwriter cannot trace back to the form is useless to them. If you find yourself proposing a metric with nothing in the submission behind it, either drop it or say plainly in the evidence field that the submission is silent on it.`,
    `- Tag it with driver slugs, as described below.`,
    ``,
    `Cover distinct dimensions of this section's risk rather than restating one dimension several ways. Prefer what this specific submission makes salient over a generic checklist.`,
    ``,
    driverBlock(knownDrivers),
    ``,
    NO_PRICING,
    ``,
    memoryBlock(memory, section),
  );

  return lines.join("\n");
}

function driverBlock(knownDrivers: string[]): string {
  const lines = [
    `Driver slugs. Each metric carries one to three short kebab-case slugs naming the underlying fact about the business that drives it - not the metric's name restated, but the thing about this client that causes it. One weakness surfacing under several cover sections at once is exactly what an underwriter needs to see, and that only works if you name it identically each time.`,
    ``,
    `Prefer these:`,
    DRIVER_VOCABULARY.map((d) => `  ${d}`).join("\n"),
  ];

  if (knownDrivers.length > 0) {
    lines.push(
      ``,
      `Already used on other sections of this same submission - reuse these verbatim wherever they apply rather than coining a variant:`,
      knownDrivers.map((d) => `  ${d}`).join("\n"),
    );
  }

  lines.push(
    ``,
    `Only coin a new slug when nothing above fits, and then keep it general enough that another section could reuse it. Never invent a slug per metric.`,
  );

  return lines.join("\n");
}

function memoryBlock(memory: MemoryEntry[], section: CoverSection): string {
  if (memory.length === 0) {
    return [
      `Accumulated underwriter corrections for the ${section.name} section: none yet. This is the first submission assessed under this section, so every metric is fresh reasoning.`,
      `Set memoryInfluenced to false and memoryBasis to an empty string on every metric, and say in memoryNote that there was no memory to draw on.`,
    ].join("\n");
  }

  return [
    `Accumulated underwriter corrections for the ${section.name} section, oldest first. These come from real underwriters reviewing your earlier proposals on other submissions under this same section. They are more authoritative than your own priors - treat them as standing instructions, not as suggestions. They apply to this section only.`,
    ``,
    `How to read each action:`,
    `- accepted: the metric and its level landed correctly. Keep proposing this metric where the submission supports it, framed the same way.`,
    `- edited: you had the metric roughly right but the name, level or framing was off. Adopt the corrected version. If the correction moved a level in a direction, carry that calibration across - assume you were reading that kind of evidence too softly or too harshly in general.`,
    `- rejected: this metric was not wanted under this section. Do not propose it again here unless this submission makes it unavoidable, and if you do, justify why in the reasoning.`,
    `- added: the underwriter had to add this themselves because you missed it. Propose it yourself now, wherever the submission gives you something to anchor it to.`,
    ``,
    ...memory.map(formatEntry),
    ``,
    `Apply these before you decide your metric set. Then, per metric, set memoryInfluenced to true only where a correction above actually changed something - which metric you proposed, its name, its level, or how you framed it - and use memoryBasis to say which correction and what it changed. Where you reasoned freshly from the submission alone, set memoryInfluenced to false and memoryBasis to an empty string. Do not overclaim memory influence; an underwriter is going to check.`,
  ].join("\n");
}

function formatEntry(entry: MemoryEntry, index: number): string {
  const parts: string[] = [
    `${index + 1}. [${entry.action}] ${entry.metricName}`,
  ];

  if (entry.action === "edited") {
    parts.push(
      `   you proposed: "${entry.proposedName ?? entry.metricName}" at level "${entry.proposedLevel ?? "(none)"}"`,
    );
    parts.push(
      `   underwriter corrected to level: "${entry.assessedLevel ?? "(none)"}"`,
    );
  } else if (entry.action === "rejected") {
    parts.push(
      `   you proposed it at level "${entry.proposedLevel ?? "(none)"}"; the underwriter threw it out`,
    );
  } else if (entry.action === "added") {
    parts.push(
      `   underwriter added it at level "${entry.assessedLevel ?? "(none)"}" - you had missed it`,
    );
  } else {
    parts.push(`   accepted at level "${entry.assessedLevel ?? "(none)"}"`);
  }

  if (entry.note) parts.push(`   underwriter's note: ${entry.note}`);
  parts.push(`   from submission: ${entry.submissionRef}`);
  return parts.join("\n");
}

export function buildSectionUserPrompt(
  submission: string,
  section: CoverSection,
): string {
  return [
    `Here is the commercial submission. Assess it for the ${section.name} section.`,
    ``,
    `<submission>`,
    submission.trim(),
    `</submission>`,
  ].join("\n");
}
