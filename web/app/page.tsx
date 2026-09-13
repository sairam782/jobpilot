import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="space-y-10">
      <section className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          Safety-first autonomous job applications.
        </h1>
        <p className="max-w-2xl text-[var(--muted)]">
          Search across 11 public job sources, score every result against your
          resume, and drive a Playwright-controlled browser through each
          application — with a human-in-the-loop gate before anything is
          submitted.
        </p>
        <div className="flex gap-3 pt-2">
          <Link
            href="/search"
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--accent-fg)]"
          >
            Start a search
          </Link>
          <Link
            href="/queue"
            className="rounded-md border border-[var(--border)] px-4 py-2 text-sm font-medium"
          >
            Review the queue
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4"
          >
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
              {f.title}
            </h2>
            <p className="mt-2 text-sm">{f.body}</p>
          </div>
        ))}
      </section>

      <section className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4 text-sm">
        <h2 className="font-semibold">Point this dashboard at your backend</h2>
        <p className="mt-2 text-[var(--muted)]">
          Set <code className="rounded bg-black/5 px-1 py-0.5 dark:bg-white/10">
            NEXT_PUBLIC_API_URL
          </code>{" "}
          on Vercel to your JobPilot API. Every page reads it at load time.
        </p>
      </section>
    </div>
  );
}

const FEATURES: { title: string; body: string }[] = [
  {
    title: "11 discovery sources",
    body:
      "Greenhouse, Lever, Ashby, Workable, SmartRecruiters, The Muse, RemoteOK, Remotive, USAJobs, Adzuna, Jooble.",
  },
  {
    title: "Deterministic scoring",
    body:
      "Title × location × skills × resume overlap with per-signal breakdown, exclusion gate, and seniority penalty.",
  },
  {
    title: "Human-in-the-loop",
    body:
      "Dry-run and require-approval defaults; every filled form parks at needs_approval until you say yes.",
  },
];
