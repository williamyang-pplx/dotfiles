---
name: e2e-test
description: Write and run a manual end-to-end test for a PR's change on a stacked branch (parent = the PR branch), exercising real hardware/services per the user's instructions, with two adversarial subagent passes (one to find potential bugs to check, one to attack the planned checks), then record the result in the PR description's Testing Strategy. Never opens a PR for the e2e branch. Use when asked to e2e test, end-to-end test, or manually verify a change against real infrastructure.
---

# End-to-end test a change

Prove that a PR's change works against the real system — real hardware, a
real account, a live service. The e2e test lives on a stacked branch, so it
does not change the PR's diff. The evidence goes in the PR description.

Model: `[Aster] Add E2BProvider` (ppl-ai/air#7919). Its Testing Strategy
points at the stacked branch `williamyang/ai-9590-e2b-e2e-manual`, run
against a real e2b.dev account.

## 0. Get the target from the user

The user must name the real system to test (hardware, account, endpoint,
environment) and what "working" looks like. If the user did not give this
context, ask before you write anything. Do not invent a target.

## 1. Identify the PR branch

Get the PR branch from `git branch --show-current` or
`gh pr view --json headRefName,baseRefName,url`. Make sure that the local
branch is current with its remote.

## 2. Adversarial pass 1: find potential bugs

Spawn a subagent to find potential bugs in the PR's implementation. Give it
the PR description, the diff, and read access to the repo. Instruct it to:

- Read each claim in the PR description, and find inputs or states that can
  disprove it.
- Examine the diff for weak points: error paths, limits, concurrency,
  teardown, and unstated assumptions about the real target.
- Return a list of potential bugs. For each bug, give the input or state
  that can trigger it.

This list sets what the e2e test must check.

## 3. Create the stacked e2e branch

Create a branch whose parent is the **PR branch**, not main:

- Name it from the slug of the PR branch: keep the ticket key, describe the
  test, and end in `-e2e-manual`. Example:
  `williamyang/ai-9590-m2-t6-e2bprovider` → `williamyang/ai-9590-e2b-e2e-manual`.
- Run `git checkout -b <e2e-branch> <pr-branch>`. If the user's checkout must
  not move, use a worktree:
  `git worktree add ../<repo>-e2e <pr-branch> -b <e2e-branch>`.

**Never open a PR for this branch — not even a draft.** Do not run
`gh pr create` for it.

## 4. Write the e2e test

On the e2e branch, write a manual test that drives the PR's change against
the real target:

- Use the real code paths through the public entry points (factory, CLI, API).
- Use the real system: credentials from environment variables, real devices,
  real network. No mocks. Do not hardcode secrets.
- Cover the main lifecycle and the edge cases that the PR description claims
  to handle.
- Add a check for each potential bug from pass 1.
- Make each step show a clear pass or fail.

Commit and push with `git push -u origin <e2e-branch>`. Do not use
/push-stacked-pr or `gh stack` for this branch — `gh stack submit` opens a PR
for each stack branch that lacks one. If the PR branch itself needs a rebase
or push, do that with /push-stacked-pr from the PR branch. Then restack the
e2e branch onto the rewritten PR branch, and push it plain again.

## 5. Adversarial pass 2: attack the planned checks

Before you run the test, spawn a second subagent to judge whether the checks
are effective. Give it the test code, the diff, and the bug list from pass 1.
Do not give it your reasoning — it must form its own view. Instruct it to
answer, for each check:

- Can the check pass when the code is broken? Find vacuous assertions,
  mocked paths, swallowed errors, and checks that only touch internal
  shortcuts.
- Does the check exercise the real target through the real entry points?
- Which potential bugs from pass 1 have no check, and which claims in the PR
  description does no check cover?

Fix each gap that the subagent reports. Commit and push the fixes the same
plain way as step 4.

## 6. Run it for real

Run the test against the real target. Correct it and run it again until it
passes. If it cannot pass — missing credentials, hardware unavailable, or a
real bug in the PR — stop and report what happened. A bug fix belongs in the
PR branch, not the e2e branch. Report the bug to the user.

## 7. Update the PR description

Invoke the `pr-authoring` skill to add the result to the description's
testing section (**Testing Strategy** if the repo's template uses that name,
otherwise **Testing**). That skill owns the format and the rules for edits to
an existing description. Give it one short bullet per run:

```
- Ran the manual e2e script (stacked branch [<e2e-branch>](https://github.com/<owner>/<repo>/compare/<pr-branch>...<e2e-branch>?expand=1)) against <the real target> — <result>
```

Name the concrete target and the outcome. If the test ran against more than
one target, write one bullet for each. Do not change the rest of the
description. If a human deleted the testing section, follow the rules of
`pr-authoring` and put the result in the final report instead.

## 8. Report

Tell the user: the e2e branch name and compare link, what the test covers,
what the two adversarial passes found, the results (failures verbatim), and
that the PR description was updated. Remind them that the e2e branch has no
PR, by design.
