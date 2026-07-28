---
name: deep-review-other-pr
description: Review a teammate's pull request for correctness, test sufficiency (including e2e coverage for mission-critical changes), duplication of existing code, missed reuse opportunities, style/convention violations, and better abstractions. Fans out subagents to search the codebase and docs. Use when asked to peer-review, review someone else's PR, or review a colleague's change. Reports findings with file:line; never posts to GitHub or pushes to the branch unless explicitly asked.
---

# Deep-review a teammate's pull request

Review someone else's PR on six axes: correctness, testing, duplication,
reusability, style, and design. This is a colleague's work, not a bot's —
assume competence, judge against the codebase's actual conventions, and
only report findings a good human reviewer would bother to write. Never
post to GitHub and never push to their branch unless explicitly asked.

## Gather context

1. Identify the PR (argument, current branch via `gh pr view`, or ask).
2. Read the description and commits — judge the diff against stated
   intent, and note what the author says about testing.
3. Fetch the diff (`gh pr diff`); never comment on untouched lines.
4. Read existing review comments to avoid duplicating feedback.
5. Fan out read-only subagents in parallel (one message, multiple Agent
   calls), each returning a detailed report:
   - **Related code** — callers and callees of every modified function,
     the types/contracts the diff touches, and how neighboring code in
     the same modules handles the same concerns (errors, config, naming).
   - **Duplication sweep** — search the codebase for existing
     implementations of what the PR adds: canonical helpers, similar
     functions in sibling modules, utilities the diff re-implements.
     Search by behavior (what it does), not just by name.
   - **Reuse candidates** — search for other places in the codebase that
     do (or per open tickets, soon will do) the same thing the PR's new
     code does, to judge whether the new code should be generalized or
     placed in a shared module instead of buried in feature code.
   - **Docs and conventions** — relevant AGENTS.md/CLAUDE.md files,
     design docs, wiki/RFC pages, and READMEs covering the touched area;
     report the documented conventions and invariants the PR must obey.
   - **Test landscape** — how the touched code is currently tested: unit
     targets, integration/e2e suites, fixtures, CI jobs. Report what
     coverage exists so gaps in the PR's testing can be judged against
     it, not against an abstract ideal.
6. Consolidate the reports into one brief — intent, related code,
   candidate duplicates, conventions, existing test coverage — and review
   against it, not just the raw diff.

## Axis 1: Correctness

Using the PR's stated intent as the spec:

- Logic: wrong operator, off-by-one, inverted condition, unreachable
  branches, code not doing what the description says.
- Edge cases: empty/None, zero, negative, unicode, timezone, first/last
  iteration, error paths.
- Error handling: swallowed exceptions, missing cleanup, resource leaks.
- State/concurrency: races, check-then-act, shared or default-arg
  mutation.
- Interface misuse: wrong argument order, mismatched types, callers not
  updated for a signature or contract change (use the related-code
  report — the bug is often in an untouched caller).
- Security: injection, secrets in code or logs, unvalidated input,
  unsafe deserialization, path traversal.

Trace each suspected bug to a concrete triggering input before keeping
it. When feasible, verify empirically: check out the PR branch in a
scratch clone or worktree and run the relevant tests or a small repro.

## Axis 2: Sufficient testing

Judge coverage against the change's blast radius, informed by the
test-landscape report:

- Every new behavior and every fixed bug needs a test that fails without
  the change. Scan the diff for branches no test reaches.
- Tests must exercise the real code: no mocking the behavior under test
  (mock only true external boundaries — network, third-party APIs, time,
  randomness); assertions must be able to fail.
- **Mission-critical or large implementation changes need end-to-end
  coverage**: if the PR rewires a serving path, storage format, training
  pipeline, or other load-bearing flow, unit tests on the new pieces are
  not enough — ask for (or point at the absence of) a test that drives
  the whole flow, and flag it prominently. A big change with only
  happy-path unit tests is a finding, not a nit.
- Match the repo's testing idioms (parametrize, existing fixtures,
  existing harnesses) rather than inventing parallel scaffolding.

## Axis 3: No repeated implementation

Every substantive piece of new code gets checked against the duplication
sweep:

- Re-implementing a canonical utility, helper, or pattern that already
  exists → point at the existing one by `file:line` and suggest using it.
- Copy-paste from elsewhere in the repo with small edits → suggest
  extracting or reusing the original.
- Duplicating constants, schemas, or config already defined once —
  especially dangerous when the two copies can drift.

Only flag with the existing implementation in hand; "this feels like it
must exist somewhere" is not a finding.

## Axis 4: Should this be reusable?

The inverse of axis 3: the PR builds something genuinely new — should it
live where others can use it?

- New logic buried in feature code that the reuse-candidates report shows
  other call sites (or concrete planned work) also need → suggest
  promoting it to the canonical shared module, named and typed for both
  callers.
- Almost-general code with one caller's assumptions baked in (hardcoded
  paths, feature-specific types in an otherwise generic function) →
  suggest the small generalization now, while it's cheap.
- But respect YAGNI: one call site and no concrete second consumer →
  leave it where it is. Speculative generality is a finding in the other
  direction.

## Axis 5: Style and convention

Judge against the local codebase's conventions (the docs-and-conventions
report), not personal taste. Flag egregious violations, not preferences:

- **Comment slop**: comments restating the next line, narrating the
  change, section headers (`# Parse the input`), or explaining the
  obvious. Top-of-file module docstrings are fine; short function
  docstrings are fine. The bar for inline comments is a non-obvious
  "why".
- AI boilerplate: emoji, hedged naming (`enhanced_`, `_v2`), defensive
  checks around code that can't fail, mid-function imports.
- Convention breaks: naming, error-handling, typing, or module-layout
  patterns that contradict what the surrounding code and the repo's
  agent/style docs establish.
- Anything a linter or CI already catches is not a finding — drop it.

## Axis 6: Broader abstractions and design

Step back from the diff: is there a reframing, existing design pattern,
or repo-native abstraction that would make this change cleaner and more
modular?

- A pattern the codebase already uses for this exact shape of problem
  (registry, visitor, config dataclass, trait/protocol, pipeline stage)
  that the PR hand-rolls around.
- A reframing that deletes whole branches, flags, or layers — behavior-
  preserving "code judo", not local polish.
- One-off modes or conditionals bolted onto shared flows where the
  existing extension point would absorb the change.
- Boundary erosion: new casts, `Any`, needless optionality, or silent
  fallbacks obscuring an invariant the old code enforced.

Only flag with a concrete alternative shape in hand, and only when the
payoff clearly exceeds the churn of restructuring someone else's nearly-
done work. "This could be more elegant" is not a finding.

## Verify before reporting

Adversarially check every candidate. Correctness: keep only with a
concrete triggering input. Testing: keep only when you can name the
untested behavior or flow. Duplication/reuse: keep only with the
existing or destination code cited by `file:line`. Style: keep only
egregious violations removal strictly improves. Design: keep only with a
specific restructuring worth the churn. Drop pre-existing issues on
unmodified lines, anything CI catches, pedantic nitpicks, likely-
intentional choices, and duplicates of existing review comments. A short
list of real findings beats a long list of maybes.

## Report

One-line verdict (approve / approve with nits / needs work), then per
finding:

- `file:line` — summary
- **Axis**: correctness (high/medium/low), testing, duplication, reuse,
  style, or design
- **Why**: correctness → triggering scenario; testing → the uncovered
  behavior; duplication/reuse → the existing or destination code;
  style/design → the convention or simpler shape
- **Fix**: concrete and minimal

Order by severity: correctness, then testing, then design, then
duplication/reuse, then style. If nothing survives, say the PR looks
good and name what you checked. Remember these findings are for William
to relay — phrase them so they can be pasted into a review as-is:
specific, respectful, no AI tells.
