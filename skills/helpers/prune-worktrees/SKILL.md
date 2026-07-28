---
name: prune-worktrees
description: Remove git worktrees in the current session's repo whose branches belong to PRs that are already merged or closed. Use when asked to prune, clean up, or remove stale/old worktrees. Only deletes clean worktrees tied to a merged/closed PR; everything else is reported, never force-removed. Never removes stacked e2e test branches still referenced by an open/draft PR.
---

# Prune worktrees for merged/closed PRs

Walk the linked worktrees of the repo this session is in and remove the ones
whose branch's PR is already merged or closed. The default posture is
conservative: a worktree is only removed when its PR is provably done AND the
worktree has nothing unsaved. Anything ambiguous gets reported, not deleted.

## 1. Enumerate the worktrees

From the session's working directory, run `git worktree list --porcelain`.
For each entry record the path, the branch (`branch refs/heads/<name>`), and
whether it's the main worktree (first entry) or the one the session is
currently inside. Those two are never removal candidates. Entries with a
detached HEAD or no branch line are skipped and mentioned in the report.

## 2. Look up each branch's PR

For each candidate branch:

```
gh pr list --head <branch> --state all --json number,state,url --limit 10
```

- **MERGED** or **CLOSED** (and no other open PR for that branch): the
  worktree is prunable.
- **OPEN** PR, or several PRs where any is open: keep.
- **No PR at all**: keep — the branch may be work that never got pushed.
  List these in the report so the user can clean them up deliberately.

## 3. Exception: e2e test branches referenced by open PRs

Stacked e2e test branches (created by the `e2e-test` skill, conventionally
suffixed `-e2e-manual` or otherwise containing `e2e` in the slug) never have
a PR of their own — they're linked from a *parent* PR's Testing Strategy
section. Their prunability follows the parent PR, not their own (absent) PR:

- For each such branch, find the PR that references it:
  `gh pr list --state all --search "<branch>" --json number,state,url`
  (and check draft PRs too — `--json` includes them). Falling back, look for
  the branch name in PR bodies of open PRs.
- Referenced by any **open or draft** PR: **keep**, even though the branch has
  no PR and looks stale. It's live evidence for an in-flight review. Flag it
  in the report as "e2e branch for open PR #N".
- Referenced only by **merged/closed** PRs: treat as prunable (subject to the
  cleanliness checks below), since the evidence link survives on the remote —
  only remove the worktree, never delete the remote branch.
- Referenced by nothing findable: keep and report, same as any no-PR branch.

## 4. Check the worktree is clean

Before removing anything, inside each prunable worktree:

- `git -C <path> status --porcelain` must be empty (no uncommitted or
  untracked changes).
- The branch must not have commits beyond what the PR merged/closed with —
  check `git -C <path> log origin/<branch>..HEAD` is empty (unpushed work).

If either check fails, don't remove it. Report it as "PR merged/closed but
worktree has local changes" and let the user decide.

## 5. Remove

For each worktree that passed both checks:

1. `git worktree remove <path>` — no `--force`; if git refuses, treat it as
   a failed cleanliness check and report instead.
2. Delete the now-orphaned local branch: `git branch -d <branch>` for merged
   PRs (`-d` is safe — it refuses unmerged work). For closed-unmerged PRs,
   leave the branch unless the user asks; deleting it discards the work.
3. Finish with `git worktree prune` to drop any stale administrative entries.

## 6. Report

One line per worktree: path, branch, PR (number + state, linked), and what
happened — removed, kept (open PR), kept (no PR), or skipped (dirty/unpushed,
with what's dirty). If nothing was prunable, say so plainly.
