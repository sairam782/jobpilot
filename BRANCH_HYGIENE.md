# Branch hygiene

Every JobPilot feature branch merges into `main` and then sits there
forever unless someone deletes it. This doc explains how to keep the
branch list clean and how to verify a branch is safe to remove.

## Current state (2026-08-26)

Eleven merged feature branches were still on the remote after the
initial burst of PRs:

| Branch | PR | Merged into `main` |
| --- | --- | --- |
| `claude/jobpilot-platform-dev-jdipgq` | #1 | ✅ |
| `bugfix/adapter-hardening` | #2 | ✅ |
| `docs/readme-rewrite` | #3 | ✅ |
| `harden/planner-json-fallback` | #4 | ✅ |
| `feat/audit-list-recent` | #5 | ✅ |
| `feat/logging-bind` | #6 | ✅ |
| `feat/resume-cli` | #7 | ✅ |
| `feat/queue-mark-many` | #8 | ✅ |
| `feat/dedup-canonicalization` | #9 | ✅ |
| `feat/audit-recent-endpoint` | #10 | ✅ |
| `feat/service-bound-logging` | #11 | ✅ |

Every commit on every branch is reachable from `origin/main`, so
deleting them removes zero work. The closed PRs stay on GitHub for
history — **deleting a branch does not delete its PR**.

## One-time cleanup

From a local checkout:

```bash
cd path/to/jobpilot
git fetch --prune origin        # syncs local view; drops refs that vanished upstream

git push origin --delete \
  bugfix/adapter-hardening \
  claude/jobpilot-platform-dev-jdipgq \
  docs/readme-rewrite \
  feat/audit-list-recent \
  feat/audit-recent-endpoint \
  feat/dedup-canonicalization \
  feat/logging-bind \
  feat/queue-mark-many \
  feat/resume-cli \
  feat/service-bound-logging \
  harden/planner-json-fallback

git fetch --prune origin        # confirm the branch list shrank
```

Or, from the GitHub UI: open
[the branches page](https://github.com/sairam782/jobpilot/branches) —
every merged branch shows a trash-can icon on the right.

## So this never accumulates again

**GitHub → Settings → General → Pull Requests → check
"Automatically delete head branches"**

Once that's on, GitHub deletes the head branch of every PR the moment
it's merged. Nothing to run, nothing to remember. Set this once and
this doc becomes historical.

## Verifying a branch is safe to delete

If you want to double-check any branch before removing it, this
one-liner exits `0` when the branch tip is reachable from `main`
(nothing lost by deleting) and non-zero otherwise:

```bash
git fetch origin
git merge-base --is-ancestor origin/<branch> origin/main \
  && echo "safe: fully on main" \
  || echo "unmerged commits present — do not delete"
```

Never force-delete an unmerged branch without confirming there is no
work you want to keep.
