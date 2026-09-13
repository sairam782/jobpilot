import type {
  EmploymentType,
  HealthResponse,
  QueueList,
  QueueRow,
  RemotePreference,
  SearchResponse,
} from "./types";

/**
 * Base URL of the JobPilot backend.
 *
 * NEXT_PUBLIC_ prefix means Next.js inlines this at build time, so the
 * bundle runs correctly on Vercel with no server-side involvement. If the
 * env var is missing at build time we fall back to a same-origin call —
 * useful for local dev when the backend is behind a reverse proxy.
 */
export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "";

export class APIError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    // The dashboard is a client-side app; we don't want Next.js caching
    // API reads. Every call goes to the network.
    cache: "no-store",
  });
  const text = await res.text();
  const body = text ? _tryParse(text) : null;
  if (!res.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText) || `HTTP ${res.status}`;
    throw new APIError(res.status, body, detail);
  }
  return body as T;
}

function _tryParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

// ---------- Public API surface -------------------------------------------

export interface SearchInput {
  roles: string[];
  locations?: string[];
  remote_preference?: RemotePreference;
  keywords?: string[];
  exclusion_keywords?: string[];
  country?: string;
  employment_types?: EmploymentType[];
  per_source_limit?: number;
  min_score?: number | null;
  top_n?: number;
  resume_text?: string;
  sources?: string[] | null;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  sources: () =>
    request<{ registered: string[]; enabled: string[] }>("/sources"),

  search: (input: SearchInput) =>
    request<SearchResponse>("/search", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  discover: (input: SearchInput) =>
    request<{
      scanned: number;
      matched: number;
      enqueued: number;
      per_source: unknown[];
      top: unknown[];
    }>("/discover", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  listQueue: (params?: { status?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.limit != null) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return request<QueueList>(`/queue${suffix}`);
  },

  getQueueItem: (id: number) => request<QueueRow>(`/queue/${id}`),

  approve: (id: number, note?: string) =>
    request<QueueRow>(`/queue/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),

  reject: (id: number, note?: string) =>
    request<QueueRow>(`/queue/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),

  skip: (id: number, note?: string) =>
    request<QueueRow>(`/queue/${id}/skip`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),

  requeue: (id: number) =>
    request<QueueRow>(`/queue/${id}/requeue`, { method: "POST" }),

  enqueue: (job: {
    url: string;
    title?: string;
    company?: string | null;
    source?: string;
    score?: number;
    metadata?: Record<string, unknown>;
  }) =>
    request<QueueRow>("/queue", {
      method: "POST",
      body: JSON.stringify({
        url: job.url,
        title: job.title ?? "Manual URL",
        company: job.company ?? null,
        source: job.source ?? "manual",
        score: job.score ?? 0.5,
        metadata: job.metadata ?? {},
      }),
    }),
};
