---
name: push-stacked-pr
description: Rebase a PR onto main and cascade that rebase up its stack using GitHub's official `gh stack` extension — restack every branch above it onto the new commits and update each PR. Use when asked to push a stack up, rebase a stacked PR, or propagate main/changes up a PR stack. Stops and asks the user before continuing past any rebase whose conflicts need a real refactor rather than a mechanical resolution; never touches main and relies on gh stack's built-in push safety (`--force-with-lease --atomic`, no bare `--force`).
---

# Push a rebase up a stack of PRs (gh stack)

Given a PR (or the branch this session is working on), sync its stack: rebase
the bottom branch onto `main`, cascade every branch above it onto the rewritten
commits, push all branches, and update the PRs — all via GitHub's official
`gh stack` extension. The one hard stop: if the rebase hits conflicts that need
a genuine refactor to resolve — not a mechanical reconciliation — abort that
step and ask the user before going further up.

This rewrites already-pushed history, so it pushes only through `gh stack`'s
own safety checks (`gh stack sync` pushes with `--force-with-lease --atomic`,
refusing to clobber a remote tip that has diverged and pushing all-or-nothing).
Never fall back to a plain `git push --force` on a stack branch. Never rewrite
or push `main`; `gh stack sync` only fast-forwards the local trunk from the
remote.

Requires `gh auth status` to be logged in and the `gh-stack` extension to be
installed (`gh extension list` should show `github/gh-stack`). If either is
missing, stop and ask the user to `gh auth login` /
`gh extension install github/gh-stack` first.

## 0. Identify the stack

Take the starting PR from the user (number, URL, or branch); if none given, use
the branch this session is working on and its PR
(`gh pr view --json number,headRefName,baseRefName,url`). `gh stack` operates
on whole stacks, so any PR in the chain identifies it; the interesting bottom
is the branch whose PR is based on `main` (go with what GitHub says the bases
are).

## 1. Make sure the stack is tracked locally

`gh stack view --short` (or `--json`) shows the stack the current branch
belongs to, if tracked. If it isn't tracked locally, `gh stack checkout
<pr-number>` discovers the stack from GitHub, fetches its branches, and sets it
up locally. If the PRs were opened without gh-stack and discovery doesn't find
a stack, adopt the branches by hand: `gh stack init <bottom> ... <top>`
(bottom to top; existing branches are adopted, the first is based on the
trunk).

Cross-check the tracked stack against GitHub's view of the chain
(`gh pr list --state open --json number,headRefName,baseRefName,url --limit 100`,
following `baseRefName → headRefName` edges from the bottom branch up) — this
catches forks (two PRs based on the same branch; gh-stack tracks linear stacks,
so handle each chain independently) and confirms the tracked order matches what
GitHub thinks the PR bases are.

Show the user the stack you found (each PR: number, branch, base, linked URL)
before rewriting anything — if it forked or GitHub and the local stack
disagreed, that's exactly what they need to see. Then proceed.

## 2. Sync (rebase + push in one)

Work in the worktree that already has a stack branch checked out
(`git worktree list` to find it). gh stack needs to check out each branch in
the stack as it rebases, so **no branch in this stack can be checked out in a
different worktree** — if one is, switch that worktree to a scratch branch
first. If no stack branch is checked out anywhere, add a scratch worktree
(`git worktree add ../<repo>-stack <branch>`) rather than moving the session's
checkout.

Then `gh stack sync` — this fetches, reconciles the local stack with the stack
on GitHub (pulling down branches for any PRs added remotely), fast-forwards the
local trunk, cascade-rebases every stack branch onto its updated parent, pushes
all branches atomically with `--force-with-lease`, and syncs PR state. No
manual `--onto` math needed; gh stack tracks each branch's parent itself.

If sync reports that the local and remote stacks have **diverged**, don't pick
an option yourself — in a non-interactive terminal it aborts without pushing;
report the divergence to the user and let them decide.

## 3. Conflict handling and the hard stop

If sync detects a rebase conflict, it restores every branch to its original
state and exits, advising `gh stack rebase`. Run `gh stack rebase` — it redoes
the cascading rebase and pauses at the conflict, same as plain `git rebase`.
Resolve conflicts that are **mechanical** — the same lines moved, an import
reordered, a rename that maps cleanly, a hunk that clearly belongs on top of
the new base. Reconcile, `git add`, then `gh stack rebase --continue`.

Stop when a conflict needs a **real refactor** — logic that has to be rewritten
to fit the new base, semantic conflicts, or so many tangled files that
resolving is a judgment call rather than a merge. Then:

1. `gh stack rebase --abort` — restores every branch in the stack exactly as it
   was before this operation started.
2. Report what the stack looked like going in, which branch blocked and why,
   and ask the user how to continue: resolve this one together now, skip it
   and stop, or hand the rest of the stack back to them. Wait for their call —
   don't guess past the blockage.

Because sync aborts cleanly on conflict and pushes atomically, it never leaves
lower branches rebased-and-pushed while a higher one is blocked. After a
successful `gh stack rebase`, run `gh stack sync` again to push the rebased
branches and update PR state.

## 4. Missing PRs

`gh stack sync` never opens pull requests — it only updates existing ones. If
a stack branch that should have a PR is missing one, that's what
`gh stack submit` is for, but be careful: submit includes **every** branch
without a PR by default, and some branches (e.g. stacked e2e test branches)
must never get one. Only run submit if the user wants the missing PR opened,
and confirm which branches it will include first.

## 5. Report

Bottom → top, one line per PR: rebased + pushed (new tip SHA), skipped
(already current / merged), or **blocked** (the conflict that stopped the
rebase). If the stack forked or GitHub and the local stack disagreed, say so.
Note that CI will rerun on every branch that was pushed and hasn't been
verified green.
