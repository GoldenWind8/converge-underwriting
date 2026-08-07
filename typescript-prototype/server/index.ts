/**
 * Minimal Express backend. Two jobs only: hold the credentials and call the
 * model. Plus a JSON file for memory, because the browser can't be trusted
 * with either.
 */

import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  COVER_SECTIONS,
  DRIVER_VOCABULARY,
  MOTOR_SUB_TYPES,
  SAMPLES,
  findSection,
} from "./domain.js";
import { MODEL } from "./model.js";
import { assessSection, determineNeeds, providerStatus } from "./provider.js";
import { createMemoryStore, parseCorrections } from "./memory.js";
import { ProposalParseError } from "./parse.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const memory = createMemoryStore(
  process.env.CU_MEMORY_FILE ?? path.join(here, "data", "memory.json"),
);

const app = express();
app.use(express.json({ limit: "1mb" }));

app.get("/api/bootstrap", (_req, res) => {
  res.json({
    sections: COVER_SECTIONS,
    motorSubTypes: MOTOR_SUB_TYPES,
    driverVocabulary: DRIVER_VOCABULARY,
    samples: SAMPLES,
    model: MODEL,
    provider: providerStatus(),
  });
});

/** Memory counts for every section at once, so the UI can badge the list. */
app.get("/api/memory", async (_req, res, next) => {
  try {
    const all = await memory.readAll();
    const counts: Record<string, number> = {};
    for (const section of COVER_SECTIONS) {
      counts[section.id] = (all[section.id] ?? []).length;
    }
    res.json({ counts });
  } catch (err) {
    next(err);
  }
});

app.get("/api/memory/:sectionId", async (req, res, next) => {
  try {
    const section = findSection(req.params.sectionId);
    if (!section)
      return res.status(404).json({ error: "unknown cover section" });
    res.json({ entries: await memory.read(section.id) });
  } catch (err) {
    next(err);
  }
});

/** Stage 1: which sections does this business need? */
app.post("/api/needs", async (req, res, next) => {
  try {
    const submission = req.body?.submission;
    if (typeof submission !== "string" || submission.trim().length < 20) {
      return res.status(400).json({
        error: "submission must be at least 20 characters of client detail",
      });
    }

    const { needs, cost } = await determineNeeds(submission);
    res.json({ ...needs, costUsd: cost.costUsd });
  } catch (err) {
    next(err);
  }
});

/** Stage 2: assess one section, on demand. Never fans out on its own. */
app.post("/api/assess", async (req, res, next) => {
  try {
    const { sectionId, submission, knownDrivers, needReason, motorSubType } =
      req.body ?? {};

    const section = findSection(String(sectionId ?? ""));
    if (!section) {
      return res.status(400).json({ error: "unknown or missing sectionId" });
    }
    if (typeof submission !== "string" || submission.trim().length < 20) {
      return res.status(400).json({
        error: "submission must be at least 20 characters of client detail",
      });
    }

    const entries = await memory.read(section.id);
    const { proposal, cost } = await assessSection({
      section,
      submission,
      memory: entries,
      knownDrivers: Array.isArray(knownDrivers)
        ? knownDrivers.filter((d): d is string => typeof d === "string")
        : [],
      needReason: typeof needReason === "string" ? needReason : null,
      motorSubType: typeof motorSubType === "string" ? motorSubType : null,
    });

    res.json({
      sectionId: section.id,
      ...proposal,
      memoryEntriesUsed: entries.length,
      costUsd: cost.costUsd,
    });
  } catch (err) {
    next(err);
  }
});

/** The human's corrections, remembered against one section. */
app.post("/api/review", async (req, res, next) => {
  try {
    const { sectionId, submissionRef, corrections } = req.body ?? {};
    const section = findSection(String(sectionId ?? ""));
    if (!section) {
      return res.status(400).json({ error: "unknown or missing sectionId" });
    }

    const parsed = parseCorrections(corrections);
    const ref =
      typeof submissionRef === "string" && submissionRef.trim() !== ""
        ? submissionRef.trim().slice(0, 120)
        : "(unlabelled submission)";

    res.json({ entries: await memory.append(section.id, ref, parsed) });
  } catch (err) {
    next(err);
  }
});

app.post("/api/memory/:sectionId/clear", async (req, res, next) => {
  try {
    const section = findSection(req.params.sectionId);
    if (!section)
      return res.status(404).json({ error: "unknown cover section" });
    res.json({ entries: await memory.clear(section.id) });
  } catch (err) {
    next(err);
  }
});

// Every failure becomes a visible, readable error for the UI.
app.use(
  (
    err: unknown,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction,
  ) => {
    const message = err instanceof Error ? err.message : String(err);
    const raw =
      err instanceof ProposalParseError ? err.raw.slice(0, 2000) : undefined;
    console.error("[api]", message);
    res
      .status(err instanceof ProposalParseError ? 502 : 500)
      .json({ error: message, raw });
  },
);

const port = Number(process.env.PORT ?? 8787);
app.listen(port, () => {
  console.log(`[api] listening on http://localhost:${port} (model ${MODEL})`);
  console.log(`[api] memory file: ${memory.path}`);
  const provider = providerStatus();
  console.log(`[api] model provider: ${provider.label} - ${provider.detail}`);
});
