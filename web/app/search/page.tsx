"use client";

import { useCallback, useState } from "react";
import { api, APIError, type SearchInput } from "@/lib/api";
import type { EmploymentType, RemotePreference, SearchResponse } from "@/lib/types";

const DEFAULT_ROLES = [
  "AI Engineer",
  "Machine Learning Engineer",
  "Data Scientist",
  "Applied Scientist",
];

const EMPLOYMENT_OPTIONS: EmploymentType[] = [
  "full_time",
  "part_time",
  "contract",
  "internship",
  "temporary",
];

export default function SearchPage() {
  const [roles, setRoles] = useState<string>(DEFAULT_ROLES.join(", "));
  const [locations, setLocations] = useState<string>("Remote, United States");
  const [remotePref, setRemotePref] = useState<RemotePreference>("remote_or_hybrid");
  const [types, setTypes] = useState<Set<EmploymentType>>(
    new Set(["full_time", "part_time", "contract"]),
  );
  const [minScore, setMinScore] = useState<string>("0.5");
  const [topN, setTopN] = useState<string>("25");
  const [resumeText, setResumeText] = useState<string>("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);

  const toggleType = (t: EmploymentType) => {
    setTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  const submit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const input: SearchInput = {
        roles: splitCsv(roles),
        locations: splitCsv(locations),
        remote_preference: remotePref,
        employment_types: [...types],
        min_score: minScore ? Number(minScore) : null,
        top_n: topN ? Number(topN) : 25,
      };
      if (resumeText.trim()) input.resume_text = resumeText.trim();
      const res = await api.search(input);
      setResult(res);
    } catch (e) {
      setResult(null);
      setError(e instanceof APIError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [roles, locations, remotePref, types, minScore, topN, resumeText]);

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Fans out across every enabled discovery adapter, deduplicates, and
          ranks against your resume. Does not persist anything — use{" "}
          <code className="rounded bg-black/5 px-1 dark:bg-white/10">
            /discover
          </code>{" "}
          for that.
        </p>
      </section>

      <section className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4 space-y-4">
        <Field label="Roles (comma separated)">
          <input
            className={inputCls}
            value={roles}
            onChange={(e) => setRoles(e.target.value)}
            placeholder="AI Engineer, ML Engineer, Data Scientist"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Locations (comma separated)">
            <input
              className={inputCls}
              value={locations}
              onChange={(e) => setLocations(e.target.value)}
              placeholder="Remote, New York, NY"
            />
          </Field>
          <Field label="Remote preference">
            <select
              className={inputCls}
              value={remotePref}
              onChange={(e) => setRemotePref(e.target.value as RemotePreference)}
            >
              <option value="remote_or_hybrid">remote_or_hybrid</option>
              <option value="remote_only">remote_only</option>
              <option value="onsite_only">onsite_only</option>
            </select>
          </Field>
        </div>

        <Field label="Employment types">
          <div className="flex flex-wrap gap-2">
            {EMPLOYMENT_OPTIONS.map((t) => {
              const on = types.has(t);
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => toggleType(t)}
                  className={
                    "rounded-full border px-3 py-1 text-xs " +
                    (on
                      ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)]"
                      : "border-[var(--border)] text-[var(--muted)]")
                  }
                >
                  {t.replace("_", " ")}
                </button>
              );
            })}
          </div>
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Min score (0..1)">
            <input
              className={inputCls}
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={minScore}
              onChange={(e) => setMinScore(e.target.value)}
            />
          </Field>
          <Field label="Top N">
            <input
              className={inputCls}
              type="number"
              min={1}
              max={500}
              step={1}
              value={topN}
              onChange={(e) => setTopN(e.target.value)}
            />
          </Field>
        </div>

        <Field label="Resume text (optional — overrides RESUME_EXPANDED_PATH)">
          <textarea
            className={inputCls + " min-h-24"}
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            placeholder="Paste your resume text here, or leave blank to use the backend default."
          />
        </Field>

        <div className="flex items-center gap-3">
          <button
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--accent-fg)] disabled:opacity-50"
            disabled={loading}
            onClick={submit}
          >
            {loading ? "Searching…" : "Run search"}
          </button>
          {error ? (
            <span className="text-sm text-[var(--danger)]">{error}</span>
          ) : null}
        </div>
      </section>

      {result ? <ResultsSection data={result} /> : null}
    </div>
  );
}

function ResultsSection({ data }: { data: SearchResponse }) {
  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          Sources
        </h2>
        <div className="mt-2 text-sm">
          scanned <strong>{data.total_before_dedup}</strong> · after dedup{" "}
          <strong>{data.total_after_dedup}</strong>
        </div>
        <ul className="mt-2 grid gap-1 text-xs sm:grid-cols-2 lg:grid-cols-3">
          {data.per_source.map((r) => (
            <li
              key={r.name}
              className="flex items-center justify-between gap-2 rounded border border-[var(--border)] px-2 py-1"
            >
              <span>
                <span className="font-medium">{r.name}</span>
                <span className="ml-2 text-[var(--muted)]">
                  {r.ok ? `${r.returned} jobs` : `error: ${r.error ?? "unknown"}`}
                </span>
              </span>
              <span className="text-[var(--muted)]">{Math.round(r.took_ms)}ms</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--panel)]">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
            <tr>
              <th className="px-3 py-2">Score</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Company</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Matched skills</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((s) => (
              <tr
                key={s.job.url}
                className="border-t border-[var(--border)] align-top"
              >
                <td className="px-3 py-2 font-mono text-sm">
                  {s.score.toFixed(2)}
                </td>
                <td className="px-3 py-2">
                  <a
                    href={s.job.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-[var(--accent)] hover:underline"
                  >
                    {s.job.title}
                  </a>
                </td>
                <td className="px-3 py-2">{s.job.company ?? "—"}</td>
                <td className="px-3 py-2 text-[var(--muted)]">
                  {s.job.employment_type ?? "?"}
                </td>
                <td className="px-3 py-2 text-[var(--muted)]">{s.job.source}</td>
                <td className="px-3 py-2 text-xs text-[var(--muted)]">
                  {s.breakdown.matched_skills.slice(0, 6).join(", ") || "—"}
                </td>
              </tr>
            ))}
            {data.results.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-3 py-6 text-center text-[var(--muted)]"
                >
                  No results — try broader roles or a lower min score.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
        {label}
      </span>
      {children}
    </label>
  );
}

const inputCls =
  "w-full rounded-md border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-[var(--accent)]";

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}
