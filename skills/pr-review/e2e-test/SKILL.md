---
name: e2e-test
description: Write and run a manual end-to-end test for a PR's change on a stacked branch (parent = the PR branch), exercising real hardware/services per the user's instructions, with two adversarial subagent passes (one to find potential bugs to check, one to attack the planned checks), then record the result in the PR description's Testing Strategy. A helper script gathers research context, checks the target's credentials and reachability, enforces the stacked-branch rules, and gates the PR update on a green run that covers every potential bug. Never opens a PR for the e2e branch. Use when asked to e2e test, end-to-end test, or manually verify a change against real infrastructure.
---

# End-to-end test a change

Prove that a PR's change works against the real system — real hardware, a
real account, a live service. The e2e test lives on a stacked branch, so it
does not change the PR's diff. The evidence goes in the PR description.

Model: `[Aster] Add E2BProvider` (ppl-ai/air#7919). Its Testing Strategy
points at the stacked branch `williamyang/ai-9590-e2b-e2e-manual`, run
against a real e2b.dev account.

`<this skill's base directory>/e2e.py` does the bookkeeping: research
context, branch rules, infra checks, the coverage gate, and the report line.
Your judgment goes into the two adversarial passes, the test itself, and
the items the script lists when it exits non-zero. Do not work around a
non-zero exit, and do not update the PR description while `e2e.py report`
exits non-zero. Below, `e2e.py` means that path; run it from the repo
checkout.

## 0. Get the target from the user

The user must name the real system to test (hardware, account, endpoint,
environment) and what "working" looks like. If the user did not give this
context, ask before you write anything. Do not invent a target.

Match the target to a recipe in `<this skill's base directory>/targets/`
(`e2b`, `kitchen-devbox`). If none fits, write a recipe JSON file in the same
shape (see "Target recipes" below). Save it in `targets/` if the target will
come back, or else in the context dir from step 1.

## 1. Gather context

From the PR branch, run `e2e.py context` (or `e2e.py context <pr>`). It
checks that the local branch matches origin and GitHub's PR head, and stops
with the fix if it does not. Then it writes a context dir and prints its
path:

- `pr.md` — the PR title, body, and commits: the claims to disprove.
- `diff.patch` — the diff against the base.
- `signals.md` — env vars the diff reads, public entry points it adds or
  changes, CLI wiring, existing tests next to the changed files, e2e/smoke
  scripts already in the repo, and earlier `-e2e-manual` branches to use as
  prior art.

Rerun `context` whenever the PR branch moves.

## 2. Adversarial pass 1: find potential bugs

Spawn a subagent to find potential bugs in the PR's implementation. Give it
the context dir path and read access to the repo. Instruct it to:

- Read each claim in `pr.md`, and find inputs or states that can disprove it.
- Examine `diff.patch` for weak points: error paths, limits, concurrency,
  teardown, and unstated assumptions about the real target. Use
  `signals.md` to find the entry points and config involved.
- Return a list of potential bugs. For each bug, give the input or state
  that can trigger it.

Write the list to `<context dir>/bugs.json`:

```json
[{"id": "B1", "bug": "<one line>", "trigger": "<input or state that triggers it>"}]
```

This list sets what the e2e test must check. `e2e.py run` rejects a run that
leaves any ID unchecked.

## 3. Create the stacked e2e branch

Run `e2e.py branch --slug <slug>`, where the slug describes the test in
kebab-case (`e2b`). It keeps the PR branch's ticket key and adds
`-e2e-manual`: `williamyang/ai-9590-m2-t6-e2bprovider` →
`williamyang/ai-9590-e2b-e2e-manual`. Its parent is the PR branch, not main.
Add `--worktree` if the user's checkout must not move. It prints the
worktree path; work from there.

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
- Add a check for each potential bug in `bugs.json`.
- Print one result line per check, which `e2e.py run` parses:

  ```
  E2E PASS <check-name> covers=B1,B3 <optional detail>
  E2E FAIL <check-name> covers=B2 <what went wrong>
  ```

  `covers=` is optional for lifecycle checks that map to no bug. Exit
  non-zero if any check fails.

Commit, then push with `e2e.py push`. It refuses if the e2e branch has a PR
or if the PR branch moved past it. Do not use /push-stacked-pr or `gh stack`
for this branch — `gh stack submit` opens a PR for each stack branch that
lacks one. If the PR branch itself needs a rebase or push, do that with
/push-stacked-pr from the PR branch. Then run `e2e.py restack` and
`e2e.py push` from the e2e branch.

## 5. Adversarial pass 2: attack the planned checks

Before you run the test, spawn a second subagent to judge whether the checks
are effective. Give it the test code, the context dir's `diff.patch` and
`bugs.json`. Do not give it your reasoning — it must form its own view.
Instruct it to answer, for each check:

- Can the check pass when the code is broken? Find vacuous assertions,
  mocked paths, swallowed errors, and checks that only touch internal
  shortcuts.
- Does the check exercise the real target through the real entry points?
- Is each `covers=` honest — does the check really trigger that bug's
  `trigger`?
- Which potential bugs have no check, and which claims in `pr.md` does no
  check cover?

Fix each gap that the subagent reports. Add each uncovered claim to
`bugs.json` as a new ID, so the gate holds the test to it. Commit and push
the fixes with `e2e.py push`.

## 6. Run it for real

1. Run `e2e.py preflight <target>` (add `-p host=<devbox>` for
   `kitchen-devbox`). It checks the recipe's env vars without printing them,
   and runs its probes. If it exits non-zero, stop and ask the user to fix
   what it lists. They can run login commands here with `! <command>`.
2. Run `e2e.py run -- <test command>` from the e2e branch. It streams the
   output, saves a log, and maps each bug ID to the check that passed for it.
   It exits non-zero on any failed check, any uncovered ID, a non-zero test
   exit, or uncommitted changes.
3. Correct the test and run again until the run is green. If it cannot pass
   — missing credentials, hardware unavailable, or a real bug in the PR —
   stop and report what happened. A bug fix belongs in the PR branch, not
   the e2e branch. Report the bug to the user.

A bug that the real target cannot trigger (it needs a fault that the live
service never produces) can be resolved without a check. Add a line to
`<context dir>/resolutions.txt`:

```
<bug-id> <one-line reason the real target cannot trigger it>
```

An empty reason does not count. Use this only when no check against the
real target is possible, never to skip a check that failed.

For more than one target, run `preflight` and `run` once for each.

## 7. Update the PR description

Push, then run `e2e.py report`. It exits non-zero unless the latest run for
each target is green, tested the pushed tip of the e2e branch, and includes
the current PR head. When it passes, it prints one bullet for each target:

```
- Ran the manual e2e script (stacked branch [<e2e-branch>](<compare link>)) against <the real target> — <result>
```

The default result is a check count. Pass `--result "<outcome>"` to say what
the run proved in plain words.

Invoke the `pplx-aster:pr-authoring` skill to add those bullets to the
description's testing section (**Testing Strategy** if the repo's template
uses that name, otherwise **Testing**). That skill owns the format and the
rules for edits to an existing description. Do not change the rest of the
description. After the update, invoke the /shorten-pr-description skill as
the final pass; its invoked-from-another-skill rules keep the testing
section and the bullets you just added. If a human deleted the testing
section, follow the rules of `pplx-aster:pr-authoring` and put the result in
the final report instead.

## 8. Report

Tell the user: the e2e branch name and compare link, what the test covers,
what the two adversarial passes found, the results (failures verbatim), any
bug IDs resolved without a check and why (`report` lists them), and that the
PR description was updated. Remind them that the e2e branch has no PR, by
design.

## Target recipes

A recipe is a JSON file that says how to confirm a real target is ready:

```json
{
  "description": "the `{host}` devbox",
  "params": ["host"],
  "env": {"E2B_API_KEY": "how the user gets it"},
  "probes": [{"name": "devbox answers over SSH", "cmd": "ssh -o BatchMode=yes {host} true", "fix": "what to ask the user", "timeout": 30}]
}
```

- `description` goes into the Testing Strategy bullet after "against".
- `params` are filled from `-p key=value` into `description`, `cmd`, and `fix`.
- `env` lists the variables that must be set. Their values are never printed.
- Each probe is a shell command that exits 0 when the target is ready. Only
  its exit code and last stderr line are shown, so a probe can use a secret
  from the environment.
