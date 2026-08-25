---
name: e2e-test
description: Write and run a manual end-to-end test for a PR's change on a stacked branch (parent = the PR branch), exercising real hardware/services per the user's instructions, then record the result in the PR description's Testing Strategy. Never opens a PR for the e2e branch. Use when asked to e2e test, end-to-end test, or manually verify a change against real infrastructure.
---

# End-to-end test a change

Prove a PR's change works against the real thing — real hardware, a real
external account, a live service — not just unit tests. The e2e test lives on
a stacked branch so it never pollutes the PR's diff, and the evidence lands in
the PR description.

Model: `[Aster] Add E2BProvider` (ppl-ai/air#7919), whose Testing Strategy
points at a stacked branch `williamyang/ai-9590-e2b-e2e-manual` run against a
real e2b.dev account.

## 0. Get the target from the user

The user must say what real system the test should exercise (which hardware,
account, endpoint, environment) and roughly what "working" looks like. If
they invoked this skill without that context, ask before writing anything —
do not invent a target.

## 1. Identify the PR branch

Determine the PR branch from the current checkout (`git branch --show-current`)
or `gh pr view --json headRefName,baseRefName,url`. Make sure the local branch
is current with its remote before stacking on it.

## 2. Create the stacked e2e branch

Create a new branch whose parent is the **PR branch** (not main):

- Name it by suffixing the PR branch's slug, e.g.
  `williamyang/ai-9590-m2-t6-e2bprovider` → `williamyang/ai-9590-e2b-e2e-manual`
  (keep the ticket key, describe the test, end in `-e2e-manual`).
- `git checkout -b <e2e-branch> <pr-branch>` — or stack it in a dedicated
  worktree (`git worktree add ../<repo>-e2e <pr-branch> -b <e2e-branch>`) if
  the user's checkout shouldn't move.

**Never open a PR for this branch — not even a draft.** It exists only to be
pushed and linked. Do not run `gh pr create` for it under any circumstances.

## 3. Write the e2e test

On the stacked branch, write a manual e2e script/test that drives the PR's
change end to end against the real target from step 0:

- Exercise the real code paths the PR added or changed — go through the
  public entry points (factory, CLI, API), not internal shortcuts.
- Hit the real system: real credentials from the environment, real devices,
  real network — no mocks, no fakes. Read credentials/config from env vars;
  never hardcode secrets.
- Cover the change's main lifecycle plus the edge cases the PR description
  claims to handle (e.g. create → execute → upload/download → teardown, error
  paths, limits).
- Make it self-reporting: clear pass/fail output per step so a human rerunning
  it can see exactly what passed.

Commit to the stacked branch and push it (`git push -u origin <e2e-branch>`).
This plain push is deliberate: do **not** route this branch through the
/push-stacked-pr skill or add it to a tracked gh stack — `gh stack submit`
opens a PR for every stack branch that lacks one, and this branch must never
get one. If the underlying PR branch itself needs rebasing or pushing, that's
a separate /push-stacked-pr
invocation from the PR branch, after which this e2e branch must be restacked
onto the rewritten PR branch before its own plain push.

## 4. Run it for real

Run the script against the real target and iterate until it passes cleanly.
If it can't pass — missing credentials, hardware unavailable, or it exposes a
real bug in the PR — stop and report exactly what happened rather than
papering over it. A bug found here belongs in the PR branch, not the e2e
branch; surface it to the user.

## 5. Update the PR description

Invoke the `pr-authoring` skill to add the result to the PR description's
testing section (**Testing Strategy** if the repo's template names it that,
otherwise **Testing**) — it owns the formatting, voice, and the rules for
updating an existing description without overwriting human edits. The
content to hand it, one short bullet per run (per the model PR):

```
- Ran the manual e2e script (stacked branch [<e2e-branch>](https://github.com/<owner>/<repo>/compare/<pr-branch>...<e2e-branch>?expand=1)) against <the real target> — <result>
```

Name the concrete target (which account, device, environment) and the
outcome. If the test was run against more than one target, one bullet each.
This is an addition to the existing description — everything else in it stays
untouched, and if a human has deleted the testing section, follow
`pr-authoring`'s rules rather than re-creating it (surface the result in
the final report instead).

## 6. Report

Tell the user: the e2e branch name and compare link, what the test covers,
the run result (with failures verbatim if any), and that the PR description
was updated. Remind them the e2e branch is pushed but has no PR, by design.
