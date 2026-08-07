/**
 * Which route the model call takes, and the two flows that use it:
 *   1. ANTHROPIC_API_KEY set        -> the Anthropic SDK (production route)
 *   2. otherwise, `claude` on PATH  -> the Claude Code CLI (local evaluation)
 *   3. otherwise                    -> a clear error
 */

import type {
  CoverSection,
  MemoryEntry,
  NeedsAssessment,
  Proposal,
} from "./domain.js";
import { parseNeeds, parseProposal } from "./parse.js";
import {
  NEEDS_SCHEMA,
  PROPOSAL_SCHEMA,
  buildNeedsSystemPrompt,
  buildNeedsUserPrompt,
  buildSectionSystemPrompt,
  buildSectionUserPrompt,
} from "./prompt.js";
import { callViaSdk, hasApiKey } from "./provider-sdk.js";
import { callViaCli, hasCliBinary } from "./provider-cli.js";

/** One model call: prompts in, JSON text out. Providers implement only this. */
export interface ModelCall {
  system: string;
  user: string;
  schema: unknown;
}

export interface ModelResult {
  text: string;
  /** USD for this call, when the provider reports it. The CLI does; the SDK does not. */
  costUsd: number | null;
  outputTokens: number | null;
}

export type ProviderId = "sdk" | "cli" | "none";

export interface ProviderStatus {
  id: ProviderId;
  label: string;
  detail: string;
  /**
   * Rough USD per section assessment, for the "assess all" warning. Measured on
   * the CLI route (claude-sonnet-5 at medium effort); an order-of-magnitude
   * figure to size a decision, not a billing number.
   */
  estimatedCostPerCallUsd: number | null;
}

// Measured over five real section assessments on the CLI route: $0.088-$0.102.
// Update this if the section prompt or effort setting changes materially.
const MEASURED_CLI_COST_PER_CALL_USD = 0.095;

export function providerStatus(): ProviderStatus {
  if (hasApiKey()) {
    return {
      id: "sdk",
      label: "Anthropic SDK",
      detail: "ANTHROPIC_API_KEY is set; calls go straight to the API.",
      estimatedCostPerCallUsd: null,
    };
  }
  if (hasCliBinary()) {
    return {
      id: "cli",
      label: "Claude Code CLI",
      detail:
        "No ANTHROPIC_API_KEY, so calls run through this machine's Claude Code login. Local evaluation only.",
      estimatedCostPerCallUsd: MEASURED_CLI_COST_PER_CALL_USD,
    };
  }
  return {
    id: "none",
    label: "none available",
    detail:
      "Set ANTHROPIC_API_KEY, or install and log in to the Claude Code CLI, then restart the server.",
    estimatedCostPerCallUsd: null,
  };
}

async function callModel(call: ModelCall, label: string): Promise<ModelResult> {
  const provider = providerStatus();
  let result: ModelResult;

  switch (provider.id) {
    case "sdk":
      result = await callViaSdk(call);
      break;
    case "cli":
      result = await callViaCli(call);
      break;
    default:
      throw new Error(
        "No model provider available. Export ANTHROPIC_API_KEY in the shell that runs `npm run dev`, or install the Claude Code CLI and log in, then restart.",
      );
  }

  console.log(
    `[api] ${label} via ${provider.id}: ` +
      `${result.costUsd === null ? "cost not reported" : `$${result.costUsd.toFixed(6)}`}` +
      `, output ${result.outputTokens ?? "?"} tokens`,
  );

  return result;
}

/* ------------------------------------------------------------------ *
 * Stage 1: needs determination
 * ------------------------------------------------------------------ */

export async function determineNeeds(
  submission: string,
): Promise<{ needs: NeedsAssessment; cost: ModelResult }> {
  const result = await callModel(
    {
      system: buildNeedsSystemPrompt(),
      user: buildNeedsUserPrompt(submission),
      schema: NEEDS_SCHEMA,
    },
    "needs determination",
  );
  return { needs: parseNeeds(result.text), cost: result };
}

/* ------------------------------------------------------------------ *
 * Stage 2: per-section risk assessment
 * ------------------------------------------------------------------ */

export async function assessSection(args: {
  section: CoverSection;
  submission: string;
  memory: MemoryEntry[];
  knownDrivers: string[];
  needReason?: string | null;
  motorSubType?: string | null;
}): Promise<{ proposal: Proposal; cost: ModelResult }> {
  const result = await callModel(
    {
      system: buildSectionSystemPrompt(args),
      user: buildSectionUserPrompt(args.submission, args.section),
      schema: PROPOSAL_SCHEMA,
    },
    `assessment of ${args.section.name}`,
  );
  return { proposal: parseProposal(result.text), cost: result };
}
