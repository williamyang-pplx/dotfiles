---
name: deep-review
description: Deep-review a pull request — yours before requesting human review, or a teammate's — for AI-generated slop, clear bugs, structural regressions, duplication of existing code, missed reuse opportunities, style/convention violations, file/project layout, and better abstractions. Fans out subagents to search the codebase and docs, then reports findings with file:line in the chat. Use when asked to deep-review, self-review, bot-review, or peer-review a PR. Never writes to GitHub for William's own PRs; on a teammate's PR, posts only when explicitly asked, and every posted comment says it came from Will's bot.
---

# Deep-review a pull request

Review a PR across every axis: AI slop a careful author wouldn't have written,
clear bugs, duplication, missed reuse, style/convention, structural quality,
and file layout. The same review runs on William's own PRs and on teammates'
PRs; only the reporting differs (see "Whose PR it is").

## In Claude Code: run the deep-review-pr workflow

1. From the PR's repo, run
   `<this skill's base directory>/prefetch.py <pr> <this skill's base directory>/SKILL.md`.
   It prints the path of a generated `run.js`.
2. Call `Workflow({scriptPath: "<that path>"})`.
3. The result's `mine` says whose PR it is. Format the returned `findings` per
   "Report" below (already in report order), then list `unverified` findings
   and `failed` stages separately. A run with either is never "clean" or
   "approve".

Without the Workflow tool (Codex), follow the steps below.

## Whose PR it is

Compare the PR author (`gh pr view <pr> --json author -q .author.login`) to the
current user (`gh api user -q .login`).

- **Own PR**: this is William's work about to go in front of a reviewer —
  catch what they'd catch first. Findings go to the chat only; never write to
  GitHub.
- **Teammate's PR**: this is a colleague's work, not a bot's — assume
  competence, judge against the codebase's actual conventions, and only report
  findings a good human reviewer would bother to write. Structure/design and
  layout findings must clearly pay for the churn of restructuring someone
  else's nearly-done work. Post to GitHub only when explicitly asked, and
  never push to their branch.

## Gather context

1. Identify the PR (argument, current branch via `gh pr view`, or ask). Record
   `owner`, `repo`, PR `number`, and the head commit SHA
   (`gh pr view --json number,headRefName,headRefOid,url`).
2. Read the description and commits — judge the diff against stated intent.
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
6. Consolidate the reports into one context brief — intent, related tickets
   and their PRs, related code, prior history, candidate duplicates, and
   conventions — and review against it, not just the raw diff.

## Axis 1: AI slop

Test for every finding: would a careful human working in this codebase have
written this? Matching existing patterns is not slop.

- **Unnecessary comments**: restating the next line, narrating the change,
  section headers (`# Parse the input`), docstrings paraphrasing the
  signature. 
  ***Exceptions***
  - Short one or two sentence docstrings for complicated functions or
  classes are FINE. 
  - Paragraph long docstrings that summarize or explain how a file works are FINE. 
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

## Axis 3: No repeated implementation

Every substantive piece of new code gets checked against the duplication sweep:

- Re-implementing a canonical utility, helper, or pattern that already exists →
  point at the existing one by `file:line` and use it instead.
- Copy-paste from elsewhere in the repo with small edits → extract or reuse the
  original.
- Duplicating constants, schemas, or config already defined once — especially
  dangerous when the two copies can drift.

Only flag with the existing implementation in hand; "this feels like it must
exist somewhere" is not a finding.

## Axis 4: Should this be reusable?

The inverse of axis 3: the PR builds something genuinely new — should it live
where others can use it?

- New logic buried in feature code that the reuse-candidates report shows other
  call sites (or concrete planned work) also need → promote it to the canonical
  shared module, named and typed for both callers.
- Almost-general code with one caller's assumptions baked in (hardcoded paths,
  feature-specific types in an otherwise generic function) → make the small
  generalization now, while it's cheap.
- But respect YAGNI: one call site and no concrete second consumer → leave it
  where it is. Speculative generality is a finding in the other direction.

## Axis 5: Style and convention

Judge against the local codebase's conventions (the docs-and-conventions
report), not personal taste. Flag egregious violations, not preferences:

- Convention breaks: naming, error-handling, typing, or module-layout patterns
  that contradict what the surrounding code and the repo's agent/style docs
  establish. (Comment slop and AI boilerplate are covered under Axis 1.)
- Anything a linter or CI already catches is not a finding — drop it.

## Axis 6: Structural quality and design

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

## Axis 7: File and project layout

Judge how the change carves code into files, and where reusable logic and
config land. Prefer this shape:

- **Small, modular files with descriptive names.** A file should be about one
  thing, and its name should say what. Flag a new or grown file that mixes a
  grab-bag of unrelated helpers in with the module's core functions — split
  the helpers out into their own well-named file rather than stapling them onto
  the core one.
- **Reusable logic lives in a utils file or folder.** When a function is used
  significantly across a module (not just once), it belongs in that module's
  `utils` file or folder, not inlined next to one caller. A single `utils.py`
  is fine until it sprawls; past that, prefer a `utils/` folder split by
  concern.
- **Centralized config.** Config values and env-var reads belong in one central
  config file per project/module where they can be tuned later — not scattered
  as literals and `os.environ[...]`/`process.env...` reads across random files.
  Flag new tunables or env lookups added outside the config file, and point at
  the config file they should move to.

Only flag with the concrete destination in hand (the file to split into, the
utils location, the config file). Match an existing project layout over
imposing this one — if the repo already has a settled convention, judge against
that and note the divergence.

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
input or sequence. Slop: keep only if removal leaves the PR strictly better.
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

## Report

1. Each finding follows:
   - **Location**: `file:line` (multi-line spans as `file:start-end`)
   - **Axis**: slop, bug (high/medium/low), duplication, reuse, style,
     structure/design, or layout
   - **Why**: bug → triggering scenario; duplication/reuse → the existing or
     destination code; slop → what a human would have written; style/design →
     the convention or simpler shape; layout → the file/utils/config
     destination it should move to
   - **Fix**: concrete and minimal
2. Order findings bugs → structure/design → layout → duplication/reuse → slop
   → style, by severity. Don't flood slop nits when structural issues exist.
3. Open with a one-line verdict — own PR: clean / minor cleanup / needs work;
   teammate's PR: approve / approve with nits / needs work — then the
   findings. If nothing survives, say the PR looks clean and name what was
   checked.

### Own PR: chat only

**Never write to GitHub**: no review comments, no inline comments, no PR
comments, no description edits, no pushes. If findings are later fixed, do not
post updates or comments to the PR about the bugs being addressed either — the
report in the chat is the only output.

### Teammate's PR: chat, then GitHub only when asked

Report in the chat first, phrased so William can paste each finding into a
review as-is: specific and respectful. Post to GitHub only when William
explicitly asks, and then:

- Post one review with inline comments
  (`gh api repos/<owner>/<repo>/pulls/<number>/reviews`, `commit_id` = head
  SHA, `event: COMMENT`). Never `APPROVE` or `REQUEST_CHANGES` unless asked.
- Start every comment the bot posts — the review body, each inline comment,
  each reply — with the line `_this is Will's bee boo bot_` so the author knows
  an agent wrote it.
- Never push to their branch.
