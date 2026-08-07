/**
 * Production route: the Anthropic SDK. Used whenever ANTHROPIC_API_KEY is set.
 * The key stays here, server-side, and never reaches the browser.
 *
 * Transport only - it knows nothing about needs or metrics. Callers supply a
 * system prompt, a user prompt and a schema, and get raw JSON text back.
 */

import Anthropic from "@anthropic-ai/sdk";
import { EFFORT, MODEL } from "./model.js";
import { ProposalParseError } from "./parse.js";
import type { ModelCall, ModelResult } from "./provider.js";

const MAX_TOKENS = 8000;

let client: Anthropic | null = null;

function getClient(): Anthropic {
  if (!hasApiKey()) {
    throw new Error("ANTHROPIC_API_KEY is not set");
  }
  client ??= new Anthropic();
  return client;
}

export function hasApiKey(): boolean {
  return Boolean(process.env.ANTHROPIC_API_KEY);
}

export async function callViaSdk(call: ModelCall): Promise<ModelResult> {
  const response = await getClient().messages.create({
    model: MODEL,
    max_tokens: MAX_TOKENS,
    system: call.system,
    output_config: {
      effort: EFFORT,
      // Schema enforced server-side, so the response is JSON by construction.
      format: {
        type: "json_schema",
        schema: call.schema as unknown as Record<string, unknown>,
      },
    },
    messages: [{ role: "user", content: call.user }],
  });

  if (response.stop_reason === "refusal") {
    throw new Error("the model declined to answer this submission");
  }

  const text = response.content
    .filter((block) => block.type === "text")
    .map((block) => (block as { text: string }).text)
    .join("");

  if (response.stop_reason === "max_tokens") {
    throw new ProposalParseError(
      `the response was cut off at the ${MAX_TOKENS}-token limit, so the JSON is incomplete`,
      text,
    );
  }

  return {
    text,
    // The Messages API does not price the call for us; report tokens instead.
    costUsd: null,
    outputTokens: response.usage.output_tokens,
  };
}
