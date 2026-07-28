---
name: push-stacked-pr
description: Rebase a PR onto main and cascade that rebase up its stack — rebase every PR stacked above it onto the new commits, force-pushing each. Use when asked to push a stack up, rebase a stacked PR, or propagate main/changes up a PR stack. Stops and asks the user before continuing past any rebase whose conflicts need a real refactor rather than a mechanical resolution; never touches main and only force-pushes with lease.
---

# Push a rebase up a stack of PRs

Given a PR (or the branch this session is working on) at the bottom, rebase it
onto `main` and then walk the stack upward, rebasing each PR that sits above it
onto the rewritten commits below, force-pushing as you go. The one hard stop:
if a rebase hits conflicts that need a genuine refactor to resolve — not a
mechanical reconciliation — abort that rebase and ask the user before going
further up.

Everything here rewrites already-pushed history, so it force-pushes. Two rules
hold throughout: never rewrite or push `main`, and every force-push is
`--force-with-lease` (so a teammate's push to that branch aborts rather than
gets clobbered).

## 0. Identify the bottom of the stack

Take the starting PR from the user (number, URL, or branch); if none given, use
the branch this session is working on and its PR
(`gh pr view --json number,headRefName,baseRefName,url`). This branch is the
bottom — the one that gets rebased onto `main` (or onto its actual base if the
PR's `baseRefName` isn't `main`; go with what GitHub says the base is).

`git fetch origin` first so every base and tip below is current.

## 1. Discover the stack above it

Build the stack from both sources and reconcile them:

- **GitHub.** `gh pr list --state open --json number,headRefName,baseRefName,url --limit 100`.
  Treat it as edges `baseRefName → headRefName`. Starting from the bottom
  branch, collect every PR whose base is the bottom, then every PR based on
  *those*, and so on — the transitive descendants. The result is usually a
  linear chain but can fork (two PRs based on the same branch); handle each
  chain independently.
- **Locally.** Cross-check with `git branch` and `git log`: a local branch is
  stacked on the one below it when the lower branch's tip is an ancestor of it
  but `main` is not. Use this to catch branches whose PR is a draft or missing,
  and to confirm the GitHub chain matches what's actually on disk.

Order each chain bottom → top. Show the user the stack you found (each PR:
number, branch, base, linked URL) before rewriting anything — if it forked or
GitHub and local disagree, that's exactly what they need to see. Then proceed.

## 2. Rebase the bottom PR onto main

Work on each branch **in the worktree that already has it checked out**
(`git worktree list` to find it; `git -C <path> ...`). A stack is often spread
across worktrees, and git won't let you check a branch out twice. If a branch
isn't checked out anywhere, add a scratch worktree for it
(`git worktree add ../<repo>-stack <branch>`) rather than moving the session's
checkout.

For the bottom branch: record its current tip first
(`git rev-parse <branch>` — the ones above are still attached to this SHA),
then `git rebase origin/main`. Resolve any conflicts per §4. On success,
`git push --force-with-lease`.

## 3. Cascade the rebase up

For each branch going up the chain, its parent's history was just rewritten, so
move it onto the new commits with `--onto`:

```
git rebase --onto <parent-new-tip> <parent-old-tip> <child-branch>
```

- `<parent-old-tip>` is the SHA you recorded **before** rebasing the parent —
  the old boundary between parent and child. `<parent-new-tip>` is the parent's
  tip **after** its rebase. This replays only the child's own commits, dropping
  the parent's old ones cleanly.
- Before rebasing this child, record *its* old tip too — its own children will
  need it as their `<old-tip>`.
- Resolve conflicts per §4, then `git push --force-with-lease`.
- The PR's base on GitHub is a branch name, not a SHA, so it needs no change.
  (If GitHub ever retargeted a PR's base to `main` after a lower PR merged,
  that PR is no longer part of this stack — note it and stop treating it as a
  child.)

Repeat until the chain is exhausted (and across each chain if the stack forked).

## 4. Conflict handling and the hard stop

Resolve conflicts that are **mechanical** — the same lines moved, an import
reordered, a rename that maps cleanly, a hunk that clearly belongs on top of the
new base. Reconcile, `git add`, `git rebase --continue`.

Stop when a conflict needs a **real refactor** — logic that has to be
rewritten to fit the new base, semantic conflicts, or so many tangled files
that resolving is a judgment call rather than a merge. Then:

1. `git rebase --abort` — leave that branch exactly as it was on the remote.
2. Do **not** rebase anything above it; those branches depend on this one, so
   they can't be cascaded until it's resolved.
3. Report what's already been rebased and pushed (that work stands), which
   branch blocked and why, and ask the user how to continue: resolve this one
   together now, skip it and stop, or hand the rest of the stack back to them.
   Wait for their call — don't guess past the blockage.

## 5. Report

Bottom → top, one line per PR: rebased + pushed (new tip SHA), skipped (already
current / merged), or **blocked** (the conflict that stopped the cascade), plus
any branches above a block that were left untouched. If the stack forked or
local and GitHub disagreed, say so. Note that CI will rerun on every branch you
force-pushed and hasn't been verified green.
