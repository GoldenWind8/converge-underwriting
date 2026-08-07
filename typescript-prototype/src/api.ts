import type {
  CoverSection,
  MemoryEntry,
  NeedsAssessment,
  ProposedMetric,
  Requirement,
  Sample,
  SectionNeed,
} from "../server/domain.js";
import type { Correction } from "../server/memory.js";
import type { ProviderStatus } from "../server/provider.js";

export type {
  CoverSection,
  MemoryEntry,
  NeedsAssessment,
  ProposedMetric,
  Requirement,
  Sample,
  SectionNeed,
  Correction,
  ProviderStatus,
};

export interface MotorSubType {
  id: string;
  label: string;
  note: string;
}

export interface Bootstrap {
  sections: CoverSection[];
  motorSubTypes: MotorSubType[];
  driverVocabulary: string[];
  samples: Sample[];
  model: string;
  provider: ProviderStatus;
}

export interface NeedsResponse extends NeedsAssessment {
  costUsd: number | null;
}

export interface AssessResponse {
  sectionId: string;
  memoryNote: string;
  metrics: ProposedMetric[];
  memoryEntriesUsed: number;
  costUsd: number | null;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { "content-type": "application/json" } : undefined,
  });
  const body = await res.text();
  let parsed: unknown;
  try {
    parsed = body ? JSON.parse(body) : {};
  } catch {
    throw new Error(`${res.status} ${res.statusText}: ${body.slice(0, 300)}`);
  }
  if (!res.ok) {
    const err = parsed as { error?: string; raw?: string };
    throw new Error(
      [
        err.error ?? `request failed with ${res.status}`,
        err.raw && `\n\nmodel returned:\n${err.raw}`,
      ]
        .filter(Boolean)
        .join(""),
    );
  }
  return parsed as T;
}

export const api = {
  bootstrap: () => request<Bootstrap>("/api/bootstrap"),

  memoryCounts: () =>
    request<{ counts: Record<string, number> }>("/api/memory"),

  memory: (sectionId: string) =>
    request<{ entries: MemoryEntry[] }>(`/api/memory/${sectionId}`),

  needs: (submission: string) =>
    request<NeedsResponse>("/api/needs", {
      method: "POST",
      body: JSON.stringify({ submission }),
    }),

  assess: (args: {
    sectionId: string;
    submission: string;
    knownDrivers: string[];
    needReason: string | null;
    motorSubType: string | null;
  }) =>
    request<AssessResponse>("/api/assess", {
      method: "POST",
      body: JSON.stringify(args),
    }),

  review: (
    sectionId: string,
    submissionRef: string,
    corrections: Correction[],
  ) =>
    request<{ entries: MemoryEntry[] }>("/api/review", {
      method: "POST",
      body: JSON.stringify({ sectionId, submissionRef, corrections }),
    }),

  clearMemory: (sectionId: string) =>
    request<{ entries: MemoryEntry[] }>(`/api/memory/${sectionId}/clear`, {
      method: "POST",
    }),
};
