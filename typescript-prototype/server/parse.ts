/**
 * Validation of what comes back from the model. A malformed response must
 * surface as a visible error, not a crash or a silently empty list.
 */

import type {
  NeedsAssessment,
  Proposal,
  ProposedMetric,
  Requirement,
  SectionNeed,
} from "./domain.js";
import { COVER_SECTIONS, MOTOR_SECTION_ID, REQUIREMENTS } from "./domain.js";

export class ProposalParseError extends Error {
  readonly raw: string;
  constructor(message: string, raw: string) {
    super(message);
    this.name = "ProposalParseError";
    this.raw = raw;
  }
}

/** Shared front door: JSON text in, plain object out. */
function parseJsonObject(text: string): {
  obj: Record<string, unknown>;
  trimmed: string;
} {
  const trimmed = (text ?? "").trim();
  if (trimmed === "") {
    throw new ProposalParseError(
      "the model returned no text to parse",
      trimmed,
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (err) {
    throw new ProposalParseError(
      `the model's response was not valid JSON: ${(err as Error).message}`,
      trimmed,
    );
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new ProposalParseError(
      "expected a JSON object at the top level",
      trimmed,
    );
  }

  return { obj: parsed as Record<string, unknown>, trimmed };
}

/* ------------------------------------------------------------------ *
 * Stage 1: needs determination
 * ------------------------------------------------------------------ */

export function parseNeeds(text: string): NeedsAssessment {
  const { obj, trimmed } = parseJsonObject(text);

  if (!Array.isArray(obj.needs)) {
    throw new ProposalParseError(
      "`needs` is missing or is not an array",
      trimmed,
    );
  }
  if (obj.needs.length === 0) {
    throw new ProposalParseError("the model returned no needs", trimmed);
  }

  const seen = new Set<string>();
  const needs: SectionNeed[] = obj.needs.map((raw, i) => {
    const at = `needs[${i}]`;
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      throw new ProposalParseError(`${at} is not an object`, trimmed);
    }
    const n = raw as Record<string, unknown>;

    const sectionId = typeof n.sectionId === "string" ? n.sectionId.trim() : "";
    if (!COVER_SECTIONS.some((s) => s.id === sectionId)) {
      throw new ProposalParseError(
        `${at}.sectionId "${String(n.sectionId)}" is not one of the cover sections`,
        trimmed,
      );
    }
    if (seen.has(sectionId)) {
      throw new ProposalParseError(
        `${at}.sectionId "${sectionId}" appears more than once`,
        trimmed,
      );
    }
    seen.add(sectionId);

    const requirement = typeof n.requirement === "string" ? n.requirement : "";
    if (!REQUIREMENTS.includes(requirement as Requirement)) {
      throw new ProposalParseError(
        `${at}.requirement must be one of ${REQUIREMENTS.join(", ")}`,
        trimmed,
      );
    }

    if (typeof n.reason !== "string" || n.reason.trim() === "") {
      throw new ProposalParseError(
        `${at}.reason must be a non-empty string`,
        trimmed,
      );
    }

    // A sub-type only means anything on the motor section.
    const rawSubType =
      typeof n.motorSubType === "string" ? n.motorSubType.trim() : "";
    const motorSubType =
      sectionId === MOTOR_SECTION_ID && rawSubType !== "" ? rawSubType : null;

    return {
      sectionId,
      requirement: requirement as Requirement,
      reason: n.reason.trim(),
      motorSubType,
    };
  });

  // The model is asked for all 18. Missing ones default to not-applicable with
  // that stated plainly, rather than silently vanishing from the analysis.
  for (const section of COVER_SECTIONS) {
    if (!seen.has(section.id)) {
      needs.push({
        sectionId: section.id,
        requirement: "not-applicable",
        reason: "The model did not return an entry for this section.",
        motorSubType: null,
      });
    }
  }

  needs.sort((a, b) => sectionOrder(a.sectionId) - sectionOrder(b.sectionId));

  return {
    businessNote:
      typeof obj.businessNote === "string" ? obj.businessNote.trim() : "",
    needs,
  };
}

function sectionOrder(id: string): number {
  return COVER_SECTIONS.findIndex((s) => s.id === id);
}

/* ------------------------------------------------------------------ *
 * Stage 2: per-section risk assessment
 * ------------------------------------------------------------------ */

export function parseProposal(text: string): Proposal {
  const { obj, trimmed } = parseJsonObject(text);

  if (!Array.isArray(obj.metrics)) {
    throw new ProposalParseError(
      "`metrics` is missing or is not an array",
      trimmed,
    );
  }
  if (obj.metrics.length === 0) {
    throw new ProposalParseError("the model proposed no metrics", trimmed);
  }

  const metrics = obj.metrics.map((raw, i) => parseMetric(raw, i, trimmed));

  return {
    memoryNote: typeof obj.memoryNote === "string" ? obj.memoryNote : "",
    metrics,
  };
}

const REQUIRED_STRINGS = [
  "name",
  "assessedLevel",
  "reasoning",
  "evidence",
] as const;

function parseMetric(
  raw: unknown,
  index: number,
  source: string,
): ProposedMetric {
  const at = `metrics[${index}]`;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new ProposalParseError(`${at} is not an object`, source);
  }
  const m = raw as Record<string, unknown>;

  for (const key of REQUIRED_STRINGS) {
    const value = m[key];
    if (typeof value !== "string" || value.trim() === "") {
      throw new ProposalParseError(
        `${at}.${key} must be a non-empty string`,
        source,
      );
    }
  }

  if (typeof m.memoryInfluenced !== "boolean") {
    throw new ProposalParseError(
      `${at}.memoryInfluenced must be a boolean`,
      source,
    );
  }

  const basis =
    typeof m.memoryBasis === "string" && m.memoryBasis.trim() !== ""
      ? m.memoryBasis.trim()
      : null;

  if (m.memoryInfluenced && basis === null) {
    throw new ProposalParseError(
      `${at} claims memory influence but gives no memoryBasis`,
      source,
    );
  }

  return {
    name: (m.name as string).trim(),
    assessedLevel: (m.assessedLevel as string).trim(),
    scale: typeof m.scale === "string" ? m.scale.trim() : "",
    reasoning: (m.reasoning as string).trim(),
    evidence: (m.evidence as string).trim(),
    drivers: parseDrivers(m.drivers, at, source),
    memoryInfluenced: m.memoryInfluenced,
    // A metric that did not use memory carries no basis, whatever the model said.
    memoryBasis: m.memoryInfluenced ? basis : null,
  };
}

/**
 * Drivers are the grouping key for the common-drivers view, so they are
 * normalised to kebab-case here - a slug that differs only in case or spacing
 * would silently fail to group.
 */
function parseDrivers(raw: unknown, at: string, source: string): string[] {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) {
    throw new ProposalParseError(`${at}.drivers must be an array`, source);
  }

  const slugs: string[] = [];
  for (const entry of raw) {
    if (typeof entry !== "string") {
      throw new ProposalParseError(
        `${at}.drivers must contain only strings`,
        source,
      );
    }
    const slug = entry
      .trim()
      .toLowerCase()
      .replace(/[\s_]+/g, "-")
      .replace(/[^a-z0-9-]/g, "")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "");
    if (slug !== "" && !slugs.includes(slug)) slugs.push(slug);
  }
  return slugs;
}
