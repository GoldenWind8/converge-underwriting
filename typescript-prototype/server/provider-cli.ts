/**
 * Local-evaluation route: the Claude Code CLI, using whatever login the
 * machine already has. Used only when ANTHROPIC_API_KEY is absent.
 *
 * Transport only, same as the SDK route: system prompt, user prompt, schema in;
 * raw JSON text out. Not a production route - it depends on an interactive
 * user's credentials.
 */

import { spawn, spawnSync } from "node:child_process";
import { EFFORT, MODEL } from "./model.js";
import { ProposalParseError } from "./parse.js";
import type { ModelCall, ModelResult } from "./provider.js";

const BIN = "claude";
const TIMEOUT_MS = Number(process.env.CU_CLI_TIMEOUT_MS ?? 240_000);

/** The envelope `--output-format json` prints. Only the fields we rely on. */
interface CliEnvelope {
  is_error?: boolean;
  result?: unknown;
  total_cost_usd?: number;
  usage?: { output_tokens?: number; cache_creation_input_tokens?: number };
}

let cached: boolean | null = null;

export function hasCliBinary(): boolean {
  if (cached !== null) return cached;
  const probe = spawnSync(BIN, ["--version"], { stdio: "ignore" });
  cached = probe.status === 0;
  return cached;
}

export async function callViaCli(call: ModelCall): Promise<ModelResult> {
  const argv = [
    "--print",
    "--output-format",
    "json",
    "--model",
    MODEL,
    "--effort",
    EFFORT,
    // Replace, never append: Claude Code's default agent prompt is large and
    // irrelevant here, and appending would leave the model reading agent
    // instructions while assessing an insurance risk.
    "--system-prompt",
    call.system,
    "--exclude-dynamic-system-prompt-sections",
    // This is one text-in / JSON-out call. The model gets no tools at all.
    "--tools",
    "",
    // Best-effort schema enforcement; output is still validated by the caller.
    "--json-schema",
    JSON.stringify(call.schema),
    // A one-shot call should not accumulate session history on the machine.
    "--no-session-persistence",
  ];

  // The submission is multi-line free text, so it goes on stdin, not argv.
  const { stdout, stderr, code, timedOut } = await run(argv, call.user);

  if (timedOut) {
    throw new Error(
      `the claude CLI did not respond within ${Math.round(TIMEOUT_MS / 1000)}s. Retry, or set ANTHROPIC_API_KEY to use the SDK route.`,
    );
  }

  let envelope: CliEnvelope;
  try {
    envelope = JSON.parse(stdout) as CliEnvelope;
  } catch {
    throw new Error(
      `the claude CLI returned output that is not a JSON envelope (exit ${code}): ${(stderr || stdout).trim().slice(0, 500)}`,
    );
  }

  if (code !== 0 || envelope.is_error) {
    throw new Error(
      `the claude CLI reported a failure (exit ${code}): ${String(
        envelope.result ?? stderr,
      )
        .trim()
        .slice(0, 500)}`,
    );
  }

  if (typeof envelope.result !== "string") {
    throw new ProposalParseError(
      "the claude CLI envelope had no text result",
      JSON.stringify(envelope).slice(0, 2000),
    );
  }

  return {
    // The CLI cannot guarantee bare JSON the way the SDK's server-side schema
    // does, so pull the object out defensively. Validation is unchanged.
    text: extractJsonObject(envelope.result),
    costUsd: envelope.total_cost_usd ?? null,
    outputTokens: envelope.usage?.output_tokens ?? null,
  };
}

function run(
  argv: string[],
  stdin: string,
): Promise<{
  stdout: string;
  stderr: string;
  code: number;
  timedOut: boolean;
}> {
  return new Promise((resolve, reject) => {
    const child = spawn(BIN, argv, { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, TIMEOUT_MS);

    child.stdout.on("data", (d: Buffer) => (stdout += d.toString()));
    child.stderr.on("data", (d: Buffer) => (stderr += d.toString()));
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(new Error(`could not run the claude CLI: ${err.message}`));
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ stdout, stderr, code: code ?? -1, timedOut });
    });

    child.stdin.on("error", () => undefined); // a killed child closes stdin early
    child.stdin.end(stdin);
  });
}

/**
 * Pull the first complete JSON object out of model text, tolerating code
 * fences and surrounding prose. Returns the input unchanged when it finds
 * nothing, so the caller's parser produces the error rather than this function.
 */
export function extractJsonObject(text: string): string {
  const withoutFences = text
    .replace(/^\s*```(?:json)?\s*/i, "")
    .replace(/\s*```\s*$/, "")
    .trim();

  if (withoutFences.startsWith("{")) {
    const balanced = takeBalancedObject(withoutFences);
    if (balanced) return balanced;
  }

  const start = withoutFences.indexOf("{");
  if (start === -1) return withoutFences;
  const balanced = takeBalancedObject(withoutFences.slice(start));
  return balanced ?? withoutFences;
}

/** Scan a leading `{...}` object, respecting strings and escapes. */
function takeBalancedObject(text: string): string | null {
  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (inString) {
      if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return text.slice(0, i + 1);
    }
  }
  return null;
}
