"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, APIError } from "@/lib/api";
import type { QueueList, QueueRow } from "@/lib/types";

const STATUS_ORDER: QueueRow["status"][] = [
  "needs_approval",
  "queued",
  "running",
  "approved",
  "submitted",
  "failed",
  "rejected",
  "skipped",
];

export default function QueuePage() {
  const [data, setData] = useState<QueueList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selected, setSelected] = useState<QueueRow | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const res = await api.listQueue({ limit: 200 });
      setData(res);
      if (selectedId != null) {
        try {
          setSelected(await api.getQueueItem(selectedId));
        } catch {
          setSelected(null);
          setSelectedId(null);
        }
      }
    } catch (e) {
      setError(e instanceof APIError ? e.message : String(e));
    }
  }, [selectedId]);

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 30_000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const openRow = useCallback(async (id: number) => {
    setSelectedId(id);
    try {
      setSelected(await api.getQueueItem(id));
    } catch (e) {
      setError(e instanceof APIError ? e.message : String(e));
    }
  }, []);

  const act = useCallback(
    async (id: number, action: "approve" | "reject" | "skip" | "requeue") => {
      const key = `${id}:${action}`;
      setBusy((b) => ({ ...b, [key]: true }));
      try {
        if (action === "approve") await api.approve(id);
        else if (action === "reject") await api.reject(id);
        else if (action === "skip") await api.skip(id);
        else if (action === "requeue") await api.requeue(id);
        await refresh();
      } catch (e) {
        setError(e instanceof APIError ? e.message : String(e));
      } finally {
        setBusy((b) => ({ ...b, [key]: false }));
      }
    },
    [refresh],
  );

  const orderedRows = useMemo(() => {
    if (!data) return [];
    const rank = new Map(STATUS_ORDER.map((s, i) => [s, i]));
    return [...data.jobs].sort(
      (a, b) =>
        (rank.get(a.status) ?? 99) - (rank.get(b.status) ?? 99) ||
        b.score - a.score,
    );
  }, [data]);

  return (
    <div className="space-y-6">
      <section className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Queue</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Rows persisted by <code>POST /discover</code> or a manual enqueue.
            Refreshes every 30s.
          </p>
        </div>
        <button
          className="rounded-md border border-[var(--border)] px-3 py-1.5 text-sm"
          onClick={refresh}
        >
          Refresh
        </button>
      </section>

      {error ? (
        <div className="rounded-md border border-[var(--danger)] bg-[var(--danger)]/10 px-3 py-2 text-sm text-[var(--danger)]">
          {error}
        </div>
      ) : null}

      {data ? <CountsBar counts={data.counts} /> : null}

      <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--panel)]">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
            <tr>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Score</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Company</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {orderedRows.map((row) => (
              <tr
                key={row.id}
                className={
                  "border-t border-[var(--border)] align-top " +
                  (selectedId === row.id ? "bg-black/5 dark:bg-white/5" : "")
                }
              >
                <td className="px-3 py-2">
                  <StatusPill status={row.status} />
                </td>
                <td className="px-3 py-2 font-mono">{row.score.toFixed(2)}</td>
                <td className="px-3 py-2">
                  <button
                    className="text-left text-[var(--accent)] hover:underline"
                    onClick={() => openRow(row.id)}
                  >
                    {row.title}
                  </button>
                </td>
                <td className="px-3 py-2">{row.company ?? "—"}</td>
                <td className="px-3 py-2 text-[var(--muted)]">{row.source}</td>
                <td className="px-3 py-2 text-right">
                  <RowActions
                    row={row}
                    busy={busy}
                    onAct={(a) => act(row.id, a)}
                  />
                </td>
              </tr>
            ))}
            {orderedRows.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-3 py-6 text-center text-[var(--muted)]"
                >
                  Queue is empty. Run{" "}
                  <a href="/search" className="text-[var(--accent)]">
                    a search
                  </a>{" "}
                  and add jobs.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {selected ? (
        <DetailDrawer
          row={selected}
          onClose={() => {
            setSelected(null);
            setSelectedId(null);
          }}
        />
      ) : null}
    </div>
  );
}

function CountsBar({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (entries.length === 0) {
    return (
      <div className="text-sm text-[var(--muted)]">Queue is empty.</div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      {entries.map(([k, v]) => (
        <span
          key={k}
          className="rounded-full border border-[var(--border)] px-3 py-1"
        >
          <span className="text-[var(--muted)]">{k}</span>{" "}
          <span className="font-mono">{v}</span>
        </span>
      ))}
    </div>
  );
}

function StatusPill({ status }: { status: QueueRow["status"] }) {
  const color: Record<QueueRow["status"], string> = {
    queued: "text-[var(--muted)] border-[var(--border)]",
    running: "text-[var(--accent)] border-[var(--accent)]",
    needs_approval: "text-[var(--warn)] border-[var(--warn)]",
    approved: "text-[var(--ok)] border-[var(--ok)]",
    submitted: "text-[var(--ok)] border-[var(--ok)]",
    rejected: "text-[var(--danger)] border-[var(--danger)]",
    skipped: "text-[var(--muted)] border-[var(--border)]",
    failed: "text-[var(--danger)] border-[var(--danger)]",
  };
  return (
    <span
      className={
        "rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider " +
        color[status]
      }
    >
      {status.replace("_", " ")}
    </span>
  );
}

function RowActions({
  row,
  busy,
  onAct,
}: {
  row: QueueRow;
  busy: Record<string, boolean>;
  onAct: (a: "approve" | "reject" | "skip" | "requeue") => void;
}) {
  const isBusy = (a: string) => Boolean(busy[`${row.id}:${a}`]);
  const btn =
    "rounded border border-[var(--border)] px-2 py-1 text-xs disabled:opacity-40";
  if (row.status === "needs_approval") {
    return (
      <div className="flex justify-end gap-1">
        <button
          className={btn + " border-[var(--ok)] text-[var(--ok)]"}
          disabled={isBusy("approve")}
          onClick={() => onAct("approve")}
        >
          {isBusy("approve") ? "…" : "approve"}
        </button>
        <button
          className={btn + " border-[var(--danger)] text-[var(--danger)]"}
          disabled={isBusy("reject")}
          onClick={() => onAct("reject")}
        >
          {isBusy("reject") ? "…" : "reject"}
        </button>
        <button
          className={btn}
          disabled={isBusy("skip")}
          onClick={() => onAct("skip")}
        >
          {isBusy("skip") ? "…" : "skip"}
        </button>
      </div>
    );
  }
  if (row.status === "queued") {
    return (
      <button
        className={btn}
        disabled={isBusy("skip")}
        onClick={() => onAct("skip")}
      >
        {isBusy("skip") ? "…" : "skip"}
      </button>
    );
  }
  if (row.status === "failed") {
    return (
      <button
        className={btn}
        disabled={isBusy("requeue")}
        onClick={() => onAct("requeue")}
      >
        {isBusy("requeue") ? "…" : "requeue"}
      </button>
    );
  }
  return <span className="text-xs text-[var(--muted)]">—</span>;
}

function DetailDrawer({
  row,
  onClose,
}: {
  row: QueueRow;
  onClose: () => void;
}) {
  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-[var(--muted)]">
            Job #{row.id}
          </div>
          <h2 className="text-lg font-semibold">{row.title}</h2>
          <div className="text-sm text-[var(--muted)]">
            {row.company ?? "—"} · {row.source}
          </div>
          <a
            href={row.url}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-1 block break-all text-xs text-[var(--accent)]"
          >
            {row.url}
          </a>
        </div>
        <button
          className="rounded-md border border-[var(--border)] px-2 py-1 text-xs"
          onClick={onClose}
        >
          Close
        </button>
      </div>

      {row.reasons.length ? (
        <div className="mt-3 flex flex-wrap gap-1 text-[10px]">
          {row.reasons.map((r) => (
            <span
              key={r}
              className="rounded bg-black/5 px-1.5 py-0.5 dark:bg-white/10"
            >
              {r}
            </span>
          ))}
        </div>
      ) : null}

      {row.error_text ? (
        <pre className="mt-3 whitespace-pre-wrap rounded bg-[var(--danger)]/10 p-3 text-xs text-[var(--danger)]">
          {row.error_text}
        </pre>
      ) : null}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Filled fields
          </h3>
          {Object.keys(row.filled_fields).length === 0 ? (
            <div className="text-xs text-[var(--muted)]">none</div>
          ) : (
            <ul className="mt-2 space-y-1 text-xs">
              {Object.entries(row.filled_fields).map(([k, v]) => (
                <li key={k}>
                  <code className="text-[var(--muted)]">{k}</code>: {String(v)}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Answer previews
          </h3>
          {row.answer_previews.length === 0 ? (
            <div className="text-xs text-[var(--muted)]">none</div>
          ) : (
            <ul className="mt-2 space-y-2 text-xs">
              {row.answer_previews.map((a, i) => (
                <li key={i} className="rounded bg-black/5 p-2 dark:bg-white/10">
                  {a}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {row.audit_entries.length ? (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs uppercase tracking-wide text-[var(--muted)]">
            Audit ({row.audit_entries.length})
          </summary>
          <pre className="mt-2 whitespace-pre-wrap rounded bg-black/5 p-3 text-xs dark:bg-white/10">
            {row.audit_entries.join("\n")}
          </pre>
        </details>
      ) : null}
    </section>
  );
}
