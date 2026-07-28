---
name: deep-review-my-pr
description: Deep-review your own pull request before requesting human review — AI-generated slop, clear bugs, structural regressions, correctness, test sufficiency (including e2e for mission-critical changes), duplication of existing code, missed reuse opportunities, style/convention violations, and better abstractions. Fans out subagents to search the codebase and docs, then posts findings as inline comments on the PR. Use when asked to deep-review, self-review, or bot-review your own PR.
---

# Deep-review your own pull request

Review your own PR before you ask a human to, across every axis: AI slop a
careful author wouldn't have written, clear bugs, structural regressions,
correctness, sufficient testing, duplication, missed reuse, style/convention,
and better abstractions. This is your work about to go in front of a
reviewer — catch what they'd catch first. Post the surviving findings as
inline comments on the PR so they're addressable in place.

## Gather context

1. Identify the PR (argument, current branch via `gh pr view`, or ask). Record
   `owner`, `repo`, PR `number`, and the head commit SHA
   (`gh pr view --json number,headRefName,headRefOid,url`) — the SHA is needed
   to anchor inline comments.
2. Read the description and commits — judge the diff against stated intent, and
   note what the description claims about testing.
3. Fetch the diff (`gh pr diff`); never comment on untouched lines.
4. Check existing review comments to avoid duplicating feedback.
5. Fan out read-only subagents in parallel (one message, multiple Agent calls),
   each returning a detailed report:
   - **Linear lineage** — if the PR references a ticket (branch name, title,
     or description): read the ticket, walk to related tickets (same project,
     parent/sub-issues, blocks/blocked-by), find the PRs that implemented
     those tickets, and report what they changed and any conventions or
     decisions this PR should be consistent with.
   - **Related code** — callers and callees of every modified function,
     similar existing implementations, canonical helpers the diff might
     duplicate, the types/contracts it touches, and how neighboring code in
     the same modules handles the same concerns (errors, config, naming).
   - **History** — `git blame` / `git log` on the changed lines and prior PRs
     touching them: a "bug" may be a deliberate fix, or already flagged.
   - **Duplication sweep** — search the codebase for existing implementations
     of what the PR adds: canonical helpers, similar functions in sibling
     modules, utilities the diff re-implements. Search by behavior (what it
     does), not just by name.
   - **Reuse candidates** — search for other places in the codebase that do
     (or per open tickets, soon will do) the same thing the PR's new code
     does, to judge whether the new code should be generalized or placed in a
     shared module instead of buried in feature code.
   - **Docs and conventions** — relevant AGENTS.md/CLAUDE.md files, design
     docs, wiki/RFC pages, and READMEs covering the touched area; report the
     documented conventions and invariants the PR must obey.
   - **Test landscape** — how the touched code is currently tested: unit
     targets, integration/e2e suites, fixtures, CI jobs. Report what coverage
     exists so gaps in the PR's testing can be judged against it, not against
     an abstract ideal.
6. Consolidate the reports into one context brief — intent, related tickets
   and their PRs, related code, prior history, candidate duplicates,
   conventions, existing test coverage — and review against it, not just the
   raw diff.

## Axis 1: AI slop

Test for every finding: would a careful human working in this codebase have
written this? Matching existing patterns is not slop.

- **Unnecessary comments**: restating the next line, narrating the change,
  section headers (`# Parse the input`), docstrings paraphrasing the
  signature. A comment must explain a non-obvious "why".
- **AI boilerplate**: emoji, hedged naming (`enhanced_`, `_v2`), defensive
  try/except or null checks around code that can't fail, re-validating
  already-typed values.
- **Low-value tests**: no assertion that would fail if the code broke;
  mocking the behavior under test (mock only true external boundaries:
  network, third-party APIs, time, randomness); tautological or
  constant-literal assertions; generated permutation bulk; duplicated cases
  that should be parameterized. Scrutinize tests as closely as production code.
- **Gratuitous helpers**: single-use helpers fragmenting a straightforward
  flow; wrappers renaming an existing API; premature abstraction. Inline beats
  a helper without real reuse or a separable concern — but check the roadmap
  first (see "Helper placement").
- **Floating imports**: imports in the middle of a function or class, or inside
  a loop. Imports belong at the top of the file unless they are conditional on
  a runtime check.
- **Unnecessary type hints**: redundant with the signature, or a trivial
  `Any`/`object`/`dict`/`list`. Type hints should clarify, not clutter.

## Axis 2: Correctness and clear bugs

Using the PR's stated intent as the spec:

- Logic: wrong operator, off-by-one, inverted condition, unreachable branches,
  code not doing what the description says.
- Edge cases: empty/None, zero, negative, unicode, timezone, first/last
  iteration, error paths.
- Error handling: swallowed exceptions, missing cleanup, resource leaks.
- State/concurrency: races, check-then-act, shared or default-arg mutation.
- Interface misuse: wrong argument order, mismatched types, callers not updated
  for a signature or contract change (use the related-code report — the bug is
  often in an untouched caller).
- Security: injection, secrets in code or logs, unvalidated input, unsafe
  deserialization, path traversal.

Trace each suspected bug to a concrete triggering input before keeping it. When
feasible, verify empirically: check out the PR branch in a scratch clone or
worktree and run the relevant tests or a small repro.

## Axis 3: Sufficient testing

Judge coverage against the change's blast radius, informed by the
test-landscape report:

- Every new behavior and every fixed bug needs a test that fails without the
  change. Scan the diff for branches no test reaches.
- Tests must exercise the real code: no mocking the behavior under test (mock
  only true external boundaries — network, third-party APIs, time, randomness);
  assertions must be able to fail.
- **Mission-critical or large implementation changes need end-to-end
  coverage**: if the PR rewires a serving path, storage format, training
  pipeline, or other load-bearing flow, unit tests on the new pieces are not
  enough — add (or flag the absence of) a test that drives the whole flow, and
  call it out prominently. A big change with only happy-path unit tests is a
  finding, not a nit.
- Match the repo's testing idioms (parametrize, existing fixtures, existing
  harnesses) rather than inventing parallel scaffolding.

## Axis 4: No repeated implementation

Every substantive piece of new code gets checked against the duplication sweep:

- Re-implementing a canonical utility, helper, or pattern that already exists →
  point at the existing one by `file:line` and use it instead.
- Copy-paste from elsewhere in the repo with small edits → extract or reuse the
  original.
- Duplicating constants, schemas, or config already defined once — especially
  dangerous when the two copies can drift.

Only flag with the existing implementation in hand; "this feels like it must
exist somewhere" is not a finding.

## Axis 5: Should this be reusable?

The inverse of axis 4: the PR builds something genuinely new — should it live
where others can use it?

- New logic buried in feature code that the reuse-candidates report shows other
  call sites (or concrete planned work) also need → promote it to the canonical
  shared module, named and typed for both callers.
- Almost-general code with one caller's assumptions baked in (hardcoded paths,
  feature-specific types in an otherwise generic function) → make the small
  generalization now, while it's cheap.
- But respect YAGNI: one call site and no concrete second consumer → leave it
  where it is. Speculative generality is a finding in the other direction.

## Axis 6: Style and convention

Judge against the local codebase's conventions (the docs-and-conventions
report), not personal taste. Flag egregious violations, not preferences:

- Convention breaks: naming, error-handling, typing, or module-layout patterns
  that contradict what the surrounding code and the repo's agent/style docs
  establish. (Comment slop and AI boilerplate are covered under Axis 1.)
- Anything a linter or CI already catches is not a finding — drop it.

## Axis 7: Structural quality and design

Does the diff make the codebase structurally better or worse? Look for "code
judo": behavior-preserving reframings that delete whole branches, helpers, or
layers — not local polish. Flag only changed code, and only with a concrete
alternative in hand.

- **Missed simplification**: a reframing would delete whole categories of
  complexity; refactors that move complexity without reducing concepts.
- **Spaghetti growth**: ad-hoc conditionals bolted onto unrelated flows; one-off
  flags or modes tangling existing control flow; edge cases dropped into
  already busy functions.
- **File bloat**: pushing a file past 1000 lines — presumptive blocker; decompose
  first.
- **Abstraction problems**: thin wrappers adding indirection without clarity;
  "magic" mechanisms hiding simple data shapes. Prefer direct, boring code.
- **Repo-native patterns**: a pattern the codebase already uses for this exact
  shape of problem (registry, visitor, config dataclass, trait/protocol,
  pipeline stage) that the PR hand-rolls around.
- **Boundary erosion**: new casts, `any`/`unknown`, needless optionality, or
  silent fallbacks obscuring the real invariant.
- **Wrong layer / duplication**: feature logic leaking into shared paths;
  bespoke helpers duplicating a canonical utility.
- **Orchestration**: needlessly serialized independent work; non-atomic updates
  where an atomic structure is obvious.

Prefer remedies that delete complexity over rearranging it. "Maybe rename this"
is not a structural finding.

## Helper placement: check the roadmap

Helper verdicts depend on what code will exist soon, not just today. When a PR
adds or extracts helpers — or buries reusable logic inside feature code —
search Linear for planned work touching the same area (open tickets for the
PR's team/project, keyword search on the changed modules) and read enough of
each candidate ticket to judge real reuse:

- One call site and no concrete ticket adding another → inline it. "Might be
  useful someday" doesn't count; only actual tickets do.
- Logic a concrete upcoming ticket will also need → promote it to the canonical
  utils/shared module now, named and typed for both callers.
- Cite the ticket ID in any finding that leans on planned work. If Linear is
  unavailable, judge on current reuse alone.

## Verify before reporting

Adversarially check each candidate. Bugs: keep only with a concrete triggering
input or sequence. Testing: keep only when you can name the untested behavior or
flow. Slop: keep only if removal leaves the PR strictly better.
Duplication/reuse: keep only with the existing or destination code cited by
`file:line`. Style: keep only egregious violations removal strictly improves.
Structure/design: keep only with a specific behavior-preserving restructuring
whose payoff exceeds the churn. Drop duplicates of existing review comments. A
short list of real findings beats a long list of maybes.

Always drop:

- Pre-existing issues on unmodified lines.
- Anything a linter, typechecker, or CI would catch.
- Pedantic nitpicks a senior engineer wouldn't make.
- Likely-intentional changes related to the PR's purpose.
- Generic quality complaints (coverage, docs) with no concrete failure or
  restructuring attached.
- Issues explicitly silenced (e.g. lint-ignore).

## Report: post inline comments to the PR

Post the surviving findings as inline review comments on the PR so each lands
on the exact line it's about. This is your own PR, so posting AI-authored
review comments on it is fine.

1. Create one pending review and attach every finding as an inline comment
   anchored to the head SHA, then submit the review as `COMMENT` (not
   `APPROVE`/`REQUEST_CHANGES`). Use the reviews API so all findings land as a
   single review rather than a flurry of notifications:

   ```
   gh api repos/{owner}/{repo}/pulls/{number}/reviews \
     -f commit_id="<head-sha>" \
     -f event="COMMENT" \
     -f body="<one-line verdict: clean / minor cleanup / needs work>" \
     -F 'comments[][path]=<file>' \
     -F 'comments[][line]=<line>' \
     -F 'comments[][side]=RIGHT' \
     -F 'comments[][body]=<finding body>'
   ```

   Repeat the four `comments[][...]` fields per finding. For a multi-line span
   use `start_line`/`line`. If the reviews API is awkward for the batch, fall
   back to one inline comment per finding via
   `gh api repos/{owner}/{repo}/pulls/{number}/comments`.
2. Each comment body follows:
   - **Axis**: slop, bug (high/medium/low), testing, duplication, reuse, style,
     or structure/design
   - **Why**: bug → triggering scenario; testing → the uncovered behavior;
     duplication/reuse → the existing or destination code; slop → what a human
     would have written; style/design → the convention or simpler shape
   - **Fix**: concrete and minimal
3. Order the review body's summary bugs → testing → structure/design →
   duplication/reuse → slop → style, by severity. Don't flood slop nits when
   structural issues exist.
4. Write comment bodies in a human voice — specific, plain, no AI tells — since
   they post under your account.
5. After posting, tell the user the verdict, how many comments were posted, and
   the review URL. If nothing survives, post no comments and say the PR looks
   clean.
