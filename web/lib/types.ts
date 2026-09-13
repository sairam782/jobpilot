// Wire shapes returned by the JobPilot FastAPI service.
// Kept in one file so pages import from here, not from ad-hoc inline types.

export type EmploymentType =
  | "full_time"
  | "part_time"
  | "contract"
  | "internship"
  | "temporary";

export type RemotePreference = "remote_only" | "remote_or_hybrid" | "onsite_only";

export interface Job {
  url: string;
  title: string;
  company: string | null;
  location: string;
  description: string;
  posted_at: string | null;
  source: string;
  remote: boolean | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  employment_type: EmploymentType | null;
  metadata: Record<string, unknown>;
}

export interface ScoreBreakdown {
  title: number;
  location: number;
  skills: number;
  resume: number;
  seniority_penalty: number;
  matched_skills: string[];
  missing_skills: string[];
  reasons: string[];
}

export interface ScoredJob {
  job: Job;
  score: number;
  breakdown: ScoreBreakdown;
}

export interface AdapterReport {
  name: string;
  ok: boolean;
  took_ms: number;
  returned: number;
  error: string | null;
}

export interface SearchResponse {
  query: Record<string, unknown>;
  total_before_dedup: number;
  total_after_dedup: number;
  per_source: AdapterReport[];
  results: ScoredJob[];
}

export interface QueueRow {
  id: number;
  url: string;
  title: string;
  company: string | null;
  source: string;
  score: number;
  status:
    | "queued"
    | "running"
    | "needs_approval"
    | "approved"
    | "submitted"
    | "rejected"
    | "skipped"
    | "failed";
  reasons: string[];
  metadata: Record<string, unknown>;
  filled_fields: Record<string, string>;
  answer_previews: string[];
  audit_entries: string[];
  error_text: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueueList {
  counts: Record<string, number>;
  jobs: QueueRow[];
}

export interface HealthResponse {
  status: string;
  version: string;
  dry_run: boolean;
  require_approval: boolean;
  stop_on_captcha: boolean;
  max_applies_per_day: number;
  queue_counts: Record<string, number>;
  rate_limit_remaining: number;
}
