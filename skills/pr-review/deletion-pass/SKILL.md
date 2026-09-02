---
name: deletion-pass
description: Aggressive deletion review of a pull request — scan the PR's code for anything that can be outright deleted (dead code, unnecessary abstractions, single-use helpers, wrappers, duplicated logic that an existing helper already covers) and remove it, verifying behavior is preserved after each cut. Use when asked to do a deletion pass, slim down a PR, find what can be deleted, or aggressively remove unnecessary code or abstractions. Deletion only — never restructures, never adds code; use refactoring-code for restructuring and quick-review/deep-review for bug hunting.
---

# Deletion pass over a pull request

Scan the PR's code with one question per line: "should this exist?" —
never "how can I improve this?" The core failure mode is refactoring code
that should be deleted, or adding abstraction to an already
over-abstracted change. Removal over refactoring, simplification over
restructuring, and the diff of this pass must be net-negative: if you are
writing more code than you are deleting, stop — you are doing it wrong.

## Scope

1. Identify the PR (argument, current branch via `gh pr view`, or ask)
   and fetch the diff (`gh pr diff` or `git diff main...HEAD`).
2. The hunting ground is code the PR adds or touches, plus code the PR
   makes dead — a caller the PR removes can orphan a helper elsewhere;
   chase those orphans and delete them too.
3. Do not delete pre-existing code the PR never touches unless the PR
   itself orphaned it. Note it as a follow-up instead.

## The kill list

Hunt these in rough order of frequency. For each hit, `grep` for all
usages before flagging it dead — never trust a single file's view.

- **Dead code** — unreachable branches, unused variables/imports/params,
  commented-out blocks, feature flags nothing reads, `_v2`/`_old`
  alternates, "coming soon" placeholders, half-finished features.
- **Single-use abstractions** — a helper, class, or module with exactly
  one caller: collapse it back into the call site. A straightforward flow
  fragmented across five tiny functions is worse than one honest one.
- **Wrappers that add no value** — functions or types that only forward
  to something else: delete and call the underlying thing directly.
- **Speculative generality** — interfaces with one implementation,
  factory-for-a-factory, strategy-with-one-strategy, config options
  nothing sets, parameters every caller passes identically, extension
  points for futures nobody scheduled. YAGNI: delete down to what the PR
  actually needs today.
- **Reinvented code** — logic the PR adds that a canonical helper,
  stdlib function, or existing utility in this codebase already provides:
  delete the bespoke version and call the existing one. (Calling an
  existing function is the one "addition" this pass allows.)
- **Duplication inside the PR** — near-duplicate functions or branches:
  merge into one and delete the rest.
- **Defensive slop** — checks for conditions that cannot occur, redundant
  type assertions, try/except around code that cannot raise, comments
  restating the code, tests that assert nothing that could fail.
- **Whole features** — a module or feature in the PR that its stated
  intent doesn't require. Half-implemented means delete, not finish.

## Guardrails

- **Chesterton's Fence.** Before cutting anything non-obvious, know why
  it exists: what calls it, what it calls, its error paths, and what
  `git log`/`git blame` say about why it was written. Never delete code
  you don't understand — flag it instead.
- **Behavior is sacred.** All inputs, outputs, side effects, and error
  behavior must remain identical. Never remove error handling to make
  code "cleaner", never weaken a check that can actually fire, never
  change public APIs or test assertions. If existing tests need edits to
  pass, you changed behavior — revert.
- **No tests, no aggressive cuts.** Check coverage first. Untested code
  still gets the obviously-safe deletions (dead code, unused imports),
  but downgrade judgment calls (collapsing abstractions, merging
  functions) to proposals and say coverage is the blocker.
- **Never add code.** No new files, no new abstractions, no "event bus"
  or "registry pattern" mid-cleanup. Cleanup means less code.

## Execute safe-to-dangerous

Verify the baseline first: build and tests must pass before any cut. If
they don't, that's your first finding — report and stop.

1. **Safe deletes** — dead code, unused imports, orphans, commented-out
   blocks. Apply directly.
2. **Judgment cuts** — collapse single-use abstractions, strip wrappers,
   merge duplicates, replace bespoke logic with existing helpers. Apply
   when tests cover the affected paths; propose otherwise.
3. **Feature-level cuts** — deleting a whole module, feature, or public
   surface. Never apply unilaterally: present the case and wait.

Build and test after each cut, not once at the end. A cut that breaks
the build gets reverted and investigated, not patched around.

## Report

Lead with the score: lines deleted vs. lines added (target: heavily
negative), and count findings concretely — "deleted 4 wrappers, 2 dead
branches, 1 single-use class" beats vague impressions. Then:

- Applied cuts: `file:line` — what died and why it was safe.
- Proposed cuts awaiting a decision: the case for deletion, what blocks
  auto-applying (missing coverage, public API, whole feature).
- Follow-ups outside PR scope (pre-existing cruft worth its own pass).

If nothing can be deleted, say so plainly — a lean PR is a finding, not
a failure.
