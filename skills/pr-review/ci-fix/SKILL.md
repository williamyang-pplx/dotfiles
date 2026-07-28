---
name: ci-fix
description: Single pass over a PR's failing CI — read the failing checks' logs, diagnose each failure, fix the root causes, and push the fixes. Use when asked to fix CI bugs, patch up failing checks, or address CI failures on a PR.
---

# Fix a PR's CI failures

Read what's failing on a PR's CI, fix the root causes, and push. One pass:
diagnose everything that's red, fix it all, push once.

## 0. Identify the PR and check out its branch

Take the PR from the user (number, URL, or branch); if none given, use the
current branch's PR (`gh pr view --json number,headRefName,url`). Check out
the head branch and pull so it's current with its remote. If the user's
checkout shouldn't move, work in a worktree
(`git worktree add ../<repo>-ci <pr-branch>`).

Never rewrite history that's already pushed — fix forward with new commits.

## 1. Collect every failure

Wait out pending checks (`gh pr checks --watch`), then for each failing check
get the actual error, not just the check name:

- `gh run list --branch <pr-branch>` to find the run, then
  `gh run view <run-id> --log-failed` for the failing steps' logs.
- Read up from the exit — the root error is usually well above the final
  "exit code 1" line.

Triage each failure before fixing anything: real bug in the PR, a test whose
expectation the PR legitimately changed, stale branch / merge conflict with
the base (update from base instead of editing code), or flaky/infra failure
(rerun with `gh run rerun <run-id> --failed` — no code change warranted).

## 2. Fix the root causes

Reproduce locally when feasible (run the same test/lint/build command the CI
step runs) so fixes are verified, not guessed. Hard rules:

- Never fix by deleting or skipping tests, loosening assertions, adding
  lint-ignore/type-ignore suppressions, or bumping timeouts to mask a race —
  unless the user explicitly asks. If the test seems wrong rather than the
  code, say so and let the user decide.
- Keep changes scoped to the failures; no opportunistic refactoring.
- If a failure is in code the PR didn't touch and the base branch is also
  red, don't fix it silently — report it as pre-existing.

## 3. Push

Commit the fixes — one commit per logical fix, message naming the check it
addresses — and push to the PR branch.

## 4. Report

Tell the user: each failing check, its diagnosis, and the fix pushed for it
(commit SHA), plus anything rerun as flaky or flagged as pre-existing. CI will
rerun on the push; note that the result isn't verified green yet.
