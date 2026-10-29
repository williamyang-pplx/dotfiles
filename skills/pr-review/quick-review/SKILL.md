---
name: quick-review
description: Quick multi-agent review of a pull request on deep-review's three axes (correctness and bugs, simplification and project structure, style), built to finish in minutes — context is prefetched instead of researched, every finder starts at once, and each finding gets one verifier (three for high-severity bugs). Re-reviews after fixes cover only the changes since the last deep or quick review and recheck that review's findings. Use when asked for a quick review, a fast pass over a PR, or a re-review after fixes. Reports findings with file:line; never writes to GitHub for William's own PRs, and posts on a teammate's PR only when explicitly asked.
---

# Quick-review a pull request

The fast counterpart to deep-review: the same three axes, rubric, and report,
minus the stages that make deep-review slow — the research lenses, the
completeness critic and its probes, the component inventory, and bug repros.
`prefetch.py` gathers the context those lenses would have (the changed files
at head, call sites of the changed symbols, the AGENTS.md/CLAUDE.md files on
the touched paths) in seconds, and every finder starts at once. Prefer
deep-review for a first look at a large or unfamiliar PR; use this for small
PRs and for re-reviews after fixes.

## In Claude Code: run the quick-review-pr workflow

1. From the PR's repo, run
   `<this skill's base directory>/../deep-review/prefetch.py <pr> --template quick`.
   Add `--since <sha>` to re-review from a specific commit, or `--fresh` to
   ignore earlier reviews. It prints the path of a generated `run.js`.
2. Call `Workflow({scriptPath: "<that path>"})`.
3. Write the returned result, as JSON, to `result.json` next to `run.js` — the
   next re-review starts from it.
4. Report per "Report" below.

## Cold review or re-review

- **Cold**: no earlier review of this PR saved a result — review the whole
  diff. On a large PR the result's `note` suggests deep-review instead.
- **Re-review**: an earlier `/deep-review` or `/quick-review` of this PR saved
  a `result.json` (under the repo's `<git-common-dir>/deep-review/`). Review
  only the changes since that review's head commit, reuse its research
  reports as context, and recheck each of its open findings against the new
  head.

## Report

Follow deep-review's "## Report" section — finding format, order, verdict, and
its posting rules, including the bee boo bot line on teammates' PRs — plus:

- Say whether this was a cold review or a re-review (and since which commit),
  and relay the result's `note`.
- On a re-review, list each earlier finding with its status — addressed,
  partial, not addressed, no longer applies (or unchecked, if its recheck
  failed) — before the new findings.
- List `unverified` findings and `failed` stages separately. A run with either
  is never "clean" or "approve".

## Without the Workflow tool (Codex)

Do the review yourself in one pass, against deep-review's three axes and its
"Verify before reporting" bar:

1. Recall what this session already knows about the codebase — prior
   deep-review runs, files read, conventions and canonical helpers seen, past
   findings — and review against that. With no prior context, say so and skim
   the changed files plus their immediate callers; suggest deep-review if the
   PR looks large or unfamiliar.
2. Read the description, the diff (`gh pr diff`; never comment on untouched
   lines), and the existing review comments.
3. Review for bugs first (completeness, mechanism and compatibility, removed
   behavior, operational), then simplification and project structure, then
   style. Check each candidate before keeping it, and report as above.
