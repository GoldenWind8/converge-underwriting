/**
 * Memory: underwriter corrections, scoped per cover section, in one JSON file.
 * A correction on Theft never reaches Motor. No database by design - this is a
 * prototype.
 */

import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import path from "node:path";
import type { CorrectionAction, MemoryEntry } from "./domain.js";

/** sectionId -> corrections, oldest first. */
export type MemoryFile = Record<string, MemoryEntry[]>;

/** What the UI sends back for one reviewed metric. */
export interface Correction {
  action: CorrectionAction;
  metricName: string;
  assessedLevel: string | null;
  proposedName?: string | null;
  proposedLevel?: string | null;
  note?: string | null;
}

export interface MemoryStore {
  path: string;
  readAll(): Promise<MemoryFile>;
  read(sectionId: string): Promise<MemoryEntry[]>;
  append(
    sectionId: string,
    submissionRef: string,
    corrections: Correction[],
  ): Promise<MemoryEntry[]>;
  clear(sectionId: string): Promise<MemoryEntry[]>;
}

export function createMemoryStore(filePath: string): MemoryStore {
  // Serialise writes so two concurrent reviews can't clobber each other.
  let queue: Promise<unknown> = Promise.resolve();
  const serialise = <T>(fn: () => Promise<T>): Promise<T> => {
    const next = queue.then(fn, fn);
    queue = next.catch(() => undefined);
    return next;
  };

  async function readAll(): Promise<MemoryFile> {
    try {
      const raw = await readFile(filePath, "utf8");
      const parsed = JSON.parse(raw) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        return {};
      return parsed as MemoryFile;
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") return {};
      throw new Error(
        `memory file at ${filePath} could not be read: ${(err as Error).message}`,
      );
    }
  }

  async function writeAll(data: MemoryFile): Promise<void> {
    await mkdir(path.dirname(filePath), { recursive: true });
    const tmp = `${filePath}.${process.pid}.tmp`;
    await writeFile(tmp, `${JSON.stringify(data, null, 2)}\n`, "utf8");
    await rename(tmp, filePath);
  }

  return {
    path: filePath,
    readAll,

    async read(sectionId) {
      const all = await readAll();
      return all[sectionId] ?? [];
    },

    append(sectionId, submissionRef, corrections) {
      return serialise(async () => {
        const all = await readAll();
        const existing = all[sectionId] ?? [];
        const entries: MemoryEntry[] = corrections.map((c) => ({
          id: randomUUID(),
          at: new Date().toISOString(),
          action: c.action,
          metricName: c.metricName,
          assessedLevel: c.assessedLevel ?? null,
          proposedName: c.proposedName ?? null,
          proposedLevel: c.proposedLevel ?? null,
          note: c.note?.trim() ? c.note.trim() : null,
          submissionRef,
        }));
        const merged = [...existing, ...entries];
        await writeAll({ ...all, [sectionId]: merged });
        return merged;
      });
    },

    clear(sectionId) {
      return serialise(async () => {
        const all = await readAll();
        await writeAll({ ...all, [sectionId]: [] });
        return [];
      });
    },
  };
}

const ACTIONS: CorrectionAction[] = ["accepted", "edited", "rejected", "added"];

/** Validate corrections coming off the wire before they reach memory. */
export function parseCorrections(input: unknown): Correction[] {
  if (!Array.isArray(input)) throw new Error("corrections must be an array");
  if (input.length === 0) throw new Error("corrections must not be empty");

  return input.map((raw, i) => {
    const at = `corrections[${i}]`;
    if (!raw || typeof raw !== "object")
      throw new Error(`${at} must be an object`);
    const c = raw as Record<string, unknown>;

    const action = c.action;
    if (
      typeof action !== "string" ||
      !ACTIONS.includes(action as CorrectionAction)
    ) {
      throw new Error(`${at}.action must be one of ${ACTIONS.join(", ")}`);
    }

    const metricName = c.metricName;
    if (typeof metricName !== "string" || metricName.trim() === "") {
      throw new Error(`${at}.metricName must be a non-empty string`);
    }

    const level = optionalString(c.assessedLevel, `${at}.assessedLevel`);
    if (action !== "rejected" && !level) {
      throw new Error(
        `${at}.assessedLevel is required unless the metric is rejected`,
      );
    }

    return {
      action: action as CorrectionAction,
      metricName: metricName.trim(),
      assessedLevel: level,
      proposedName: optionalString(c.proposedName, `${at}.proposedName`),
      proposedLevel: optionalString(c.proposedLevel, `${at}.proposedLevel`),
      note: optionalString(c.note, `${at}.note`),
    };
  });
}

function optionalString(value: unknown, at: string): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string")
    throw new Error(`${at} must be a string when present`);
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}
