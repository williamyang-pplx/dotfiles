---
name: rebase-with-parent
description: Rebase a single PR branch onto its parent branch (the PR's base — main or another PR's branch in a stack) and resolve every mechanical conflict along the way. Use when asked to rebase a PR with/onto its parent, catch a branch up to its base, or fix "branch is out-of-date with base" on one PR. Stops and asks the user before resolving any conflict that needs a real refactor rather than a mechanical resolution; pushes only with `--force-with-lease` and never rewrites the parent branch. For cascading a rebase up a whole stack of PRs, use push-stacked-pr instead.
---

# Rebase a PR branch onto its parent

Given a PR (or the branch this session is working on), rebase that one branch
onto the current tip of its parent — the branch its PR is based on — resolving
conflicts that are mechanical and stopping for any that need real judgment,
then push the rewritten branch back to its PR.

This rewrites already-pushed history, so push only with
`git push --force-with-lease` — never a bare `--force`. Never rewrite or push
the parent branch itself, and never run this on `main`.

Requires `gh auth status` to be logged in. If it isn't, stop and ask the user
to `gh auth login` first.

## 0. Identify the branch and its parent

Take the PR from the user (number, URL, or branch name); if none given, use
the branch this session is working on. Then:

- `gh pr view <ref> --json number,headRefName,baseRefName,url,state` — the
  parent is `baseRefName`. Trust GitHub's base over any local assumption.
- If the branch has no open PR, ask the user which parent to rebase onto
  rather than guessing `main`.
- If the PR is closed or merged, stop and tell the user — rebasing it is
  almost certainly not what they want.

**Check for children before rewriting.** If another open PR uses this branch
as *its* base (`gh pr list --state open --json number,headRefName,baseRefName
--limit 100`, look for `baseRefName == headRefName` of this PR), this branch
is mid-stack: rebasing it alone strands the child on the old commits. If the
repo tracks the stack with `gh stack` (check `gh stack view --short`), hand
off to the push-stacked-pr skill / `gh stack sync` instead. Otherwise show
the user the children you found and ask before proceeding.

## 1. Set up a clean rebase

- `git fetch origin` so the parent ref is current.
- Work in a worktree where this branch is (or can be) checked out; if the
  branch is checked out in a different worktree, do the rebase there rather
  than fighting git over the checkout.
- Refuse to start on top of uncommitted changes: if `git status --porcelain`
  is dirty in that worktree, stop and ask the user whether to stash or commit
  first.
- Record the starting tip (`git rev-parse <branch>`) so the report — and any
  bail-out — can reference it. The rebase is always recoverable from this SHA
  or `ORIG_HEAD`.

Then: `git rebase origin/<parent>` (from the branch's checkout).

## 2. Resolve mechanical conflicts, stop for real ones

Resolve conflicts that are **mechanical** — the same lines moved, an import
or list reordered, a rename that maps cleanly, adjacent-but-independent edits,
a hunk that clearly belongs on top of the new base, or a conflict where one
side is a strict subset of the other. Reconcile, `git add`, then
`git rebase --continue`. Repeat for every conflicted commit.

Stop when a conflict needs a **real refactor** — logic that has to be
rewritten to fit the new base, semantic conflicts (both sides changed what
the code *means*), an API this branch uses that the parent deleted or
reshaped, or so many tangled files that resolving is a judgment call rather
than a merge. Then:

1. `git rebase --abort` — the branch is restored exactly to its starting tip.
2. Report which commit and files blocked, what the two sides each changed,
   and ask the user how to continue: resolve it together now, or hand the
   branch back. Don't guess past the blockage.

After the rebase completes, sanity-check the result: `git log --oneline
origin/<parent>..<branch>` should show the same commits as before (same
count/subjects, new SHAs), and the project's build or quick test command
should still pass if one is cheap to run — conflict resolution that compiles
is not proof, but conflict resolution that doesn't compile is proof of a
mistake.

## 3. Push and report

`git push --force-with-lease origin <branch>`. If the lease fails, the remote
tip moved since the fetch — someone else pushed. Don't retry harder; fetch,
show the user the divergence, and ask.

Report: old tip → new tip, how many commits were replayed, which conflicts
were resolved and how (one line each — the user should be able to audit every
resolution), and that CI will rerun on the PR. If anything was skipped or
stopped, lead with that.
