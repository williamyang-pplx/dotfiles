---
name: quick-review
description: Quick single-agent review of a pull request for AI slop, clear bugs, and structural quality, reusing codebase context already in this session (e.g. from prior deep-review runs) instead of re-exploring. Use when asked for a quick review, a fast pass over a PR, or a re-review after fixes. Reports findings with file:line; does not post to GitHub unless explicitly asked.
---

# Quick-review a pull request

The fast, single-agent counterpart to deep-review: same three axes (AI
slop, clear bugs, structural quality), but do the entire review yourself in
the main conversation — no subagent fan-out, no Linear walking, no history
excavation. Report findings; never post to GitHub unless explicitly asked.

## Recall before you gather

Before touching the diff, take stock of what you already know about this
codebase from earlier in the session — prior deep-review runs, files you
have read, conventions and canonical helpers you have seen, tickets and
past findings already discussed. Write yourself a short mental brief from
that recalled context and review against it; that brief is what replaces
deep-review's context-gathering fan-out.

- Prior deep-review context on the same PR or nearby code is the ideal
  case: reuse its intent summary, related-code map, and past findings, and
  check whether earlier findings were actually addressed.
- If you have no prior context on this codebase, say so in the verdict and
  fall back to a brief targeted skim — the changed files plus immediate
  callers — still without spawning subagents. Suggest deep-review if the
  PR looks large or unfamiliar.

## Gather the minimum

1. Identify the PR (argument, current branch via `gh pr view`, or ask).
2. Read the description — judge the diff against stated intent.
3. Fetch the diff (`gh pr diff`); never comment on untouched lines.
4. Skim existing review comments to avoid duplicating feedback.

## The three axes

Judge everything relative to the local codebase: matching its existing
patterns is not slop, and "structurally worse" means worse than the shape
the surrounding code already has, not worse than an abstract ideal.

- **AI slop** — would a careful human working in this codebase have
  written this? Comments restating the code or narrating the change; AI
  boilerplate (emoji, hedged naming, defensive checks around code that
  can't fail); tests with no assertion that would fail if the code broke,
  or that mock the behavior under test; single-use helpers fragmenting a
  straightforward flow; mid-function imports; type hints that clutter
  rather than clarify.
- **Clear bugs** — using the PR's stated intent as the spec: wrong
  operator, off-by-one, inverted condition; unhandled empty/None/error
  paths; swallowed exceptions and resource leaks; races and check-then-act;
  callers not updated for a signature change; injection, secrets in code
  or logs, unvalidated input.
- **Structural quality** — does the diff make the codebase structurally
  better or worse? Missed reframings that would delete whole branches or
  helpers; one-off flags tangling existing control flow; files pushed past
  1000 lines; thin wrappers adding indirection; new casts or silent
  fallbacks obscuring an invariant; bespoke helpers duplicating a
  canonical utility you know exists. Flag only changed code, and only
  with a concrete alternative in hand.

## Verify before reporting

Adversarially check each candidate. Bugs: keep only with a concrete
triggering input. Slop: keep only if removal leaves the PR strictly
better. Structure: keep only with a specific behavior-preserving
restructuring whose payoff exceeds the churn. Drop pre-existing issues on
unmodified lines, anything a linter or CI would catch, pedantic nitpicks,
likely-intentional changes, and duplicates of existing review comments. A
short list of real findings beats a long list of maybes.

## Report

One-line verdict (clean / minor cleanup / needs work), noting whether the
review leaned on prior session context or a cold skim, then per finding:

- `file:line` — summary
- **Category**: bug (high/medium/low), structure, or slop
- **Why**: bug → triggering scenario; structure → the simpler shape;
  slop → what a human would have written
- **Fix**: concrete and minimal

Order bugs, then structure, then slop, by severity. If nothing survives,
say the PR looks clean.
