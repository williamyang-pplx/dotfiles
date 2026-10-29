---
name: deep-review
description: Deep-review a pull request — yours before requesting human review, or a teammate's — on three axes - correctness and bugs (the most resourced, with repro attempts), simplification and project structure (components that don't need to exist, duplication, reuse, design, layout), and style (AI slop, conventions). Fans out subagents to search the codebase and docs, then reports findings with file:line in the chat. Use when asked to deep-review, self-review, bot-review, or peer-review a PR. Never writes to GitHub for William's own PRs; on a teammate's PR, posts only when explicitly asked, and every posted comment says it came from Will's bot.
---

# Deep-review a pull request

Review a PR on three axes: correctness and bugs, simplification and project
structure, and style. Correctness matters most and gets the most review
effort. The same review runs on William's own PRs and on teammates' PRs; only
the reporting differs (see "Whose PR it is").

## In Claude Code: run the deep-review-pr workflow

1. From the PR's repo, run
   `<this skill's base directory>/prefetch.py <pr>`.
   It prints the path of a generated `run.js`.
2. Call `Workflow({scriptPath: "<that path>"})`.
3. Write the returned result, as JSON, to `result.json` next to `run.js`, so a
   later `/quick-review` can re-review from it instead of starting cold.
4. The result's `mine` says whose PR it is. Format the returned `findings` per
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
  findings a good human reviewer would bother to write. Simplification and
  structure findings must clearly pay for the churn of restructuring someone
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
   - **Callers and contracts** — every caller and callee of each modified
     function, and every consumer of each changed signature, type, schema,
     config key, CLI flag, env var, or serialized format — across languages,
     configs, and YAML, followed at least two hops out. For each consumer,
     report whether the PR updated it and what breaks if it didn't.
   - **Neighboring patterns** — read (not just grep) the sibling code in the
     same modules and packages, and report how it handles the concerns the
     diff touches: errors, config, naming, typing, logging, data shapes, and
     extension points, each with a `file:line` example.
   - **History** — `git blame` / `git log` on the changed lines and prior PRs
     touching them: a "bug" may be a deliberate fix, or already flagged.
   - **Past review comments** — for each changed file, find the recent merged
     PRs that touched it (`git log` on the path, then the `(#123)` in the
     subjects) and read their review comments (`gh api
     repos/<owner>/<repo>/pulls/<n>/comments`). Report what reviewers
     repeatedly pushed on in this area — the bar this PR will be held to —
     quoting the comments.
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
   and their PRs, callers and contracts, neighboring patterns, prior history,
   past reviewer concerns, candidate duplicates, and conventions — and review
   against it, not just the raw diff.
7. After the first review pass, ask what it missed: changed files, contract
   consumers, or risks from the reports that no finding examined. Probe each
   gap with a fresh, targeted pass before verifying.

## Axis 1: Correctness and bugs

Using the PR's stated intent as the spec:

- Task completeness: the PR does all of what its description and linked
  ticket promise, correctly — no stubbed paths, half-wired flags, or cases the
  description names but the code skips.
- Logic: wrong operator, off-by-one, inverted condition, unreachable branches,
  code not doing what the description says.
- Edge cases: empty/None, zero, negative, unicode, timezone, first/last
  iteration, error paths.
- Error handling: swallowed exceptions, missing cleanup, resource leaks;
  silent failures (bad state or misconfig that returns a default instead of
  raising); status or retry information not propagated to the caller.
- State/concurrency: races, check-then-act, shared or default-arg mutation.
- Interface misuse: wrong argument order, mismatched types, callers not updated
  for a signature or contract change (use the callers-and-contracts report — the bug is
  often in an untouched caller).
- Compatibility: clients, SDKs, or services on the other side of an API the
  change breaks — including older versions still deployed — and persisted or
  serialized data and wire formats the new code can no longer read or write.
- Security: missing authorization (any user acting on another's resource),
  injection, secrets in code or logs, unvalidated input, unsafe
  deserialization, path traversal.
- Removed behavior: code, branches, validation, side effects, or defaults the
  PR deletes, bypasses, or stops doing that a caller, test, or runtime path
  still relies on.
- Operational: unbounded loops or waits with no timeout, retries that can
  storm, work lost or left inconsistent on cancellation, interruption, or
  partial failure, code that needs a config, secret, or migration in place
  first (deploy order, version skew), performance regressions on hot paths.

Trace each suspected bug to a concrete triggering input before keeping it. When
feasible, verify empirically: check out the PR head in a scratch worktree and
run the relevant tests or a small repro.

Give each fix as a minimal plain-text diff. Fixes belong in the PR's own
files: when a bug needs a change outside the diff (an untouched caller), anchor
the finding on the changed line that causes it and name the out-of-diff file
that must change. Size the fix to the bug — a fix that complicates the code
more than the bug costs is the wrong fix.

## Axis 2: Simplification and project structure

Does the change need all of its parts, and does it leave the codebase's
structure better or worse? Two passes: each component's right to exist, and
the shape of the change as a whole — design, duplication and reuse, and where
code and config live. Flag only changed code, and only with a concrete
behavior-preserving alternative in hand.

### Does each component need to exist?

Adapted from `/simplify`. List every component the PR adds or grows — files,
classes, functions, parameters and flags, config keys and env vars, constants,
fields and state, branches and special cases, tests, dependencies — and
challenge each one adversarially: assume it should not exist in its current
form, and try to prove it. Judge against the repo's AGENTS.md/CLAUDE.md rules
and what the codebase already has, not taste.

Challenge each component from five angles:

- **Reuse**: the codebase already does this — a shared/utility module or a
  file next to the change has the helper, type, constant, or pattern. Name it
  by `file:line` and call it instead.
- **Simplification**: complexity the job doesn't need — redundant or derivable
  state, copy-paste with slight variation, deep nesting, dead code left
  behind, a layer or helper the flow doesn't need. Name the simpler form that
  does the same job.
- **Efficiency**: work that doesn't need to happen — redundant computation or
  repeated I/O, independent operations run sequentially, blocking work added
  to startup or hot paths, long-lived closures holding a large scope. Name the
  cheaper form.
- **Altitude**: a symptom patched instead of the root cause — special cases
  layered on shared infrastructure mean the fix isn't deep enough. Name the
  change to the underlying mechanism that makes the component unnecessary.
- **Conventions**: an AGENTS.md/CLAUDE.md rule that rules the component out or
  makes it redundant (no wrappers, constants inline until shared, errors in
  `errors.py`, ...). Quote the rule and its path.

A challenge is a finding only with a behavior-preserving replacement in hand:
delete it, call `X` at `file:line`, inline it, derive it from `Y`, merge it
into `Z`, or move the fix into mechanism `M`.

### Duplication

Every substantive piece of new code gets checked against the duplication sweep:

- Re-implementing a canonical utility, helper, or pattern that already exists →
  point at the existing one by `file:line` and use it instead.
- Copy-paste from elsewhere in the repo with small edits → extract or reuse the
  original.
- Duplicating constants, schemas, or config already defined once — especially
  dangerous when the two copies can drift.

Only flag with the existing implementation in hand; "this feels like it must
exist somewhere" is not a finding.

### Reuse

The inverse of duplication: the PR builds something genuinely new — should it
live where others can use it?

- New logic buried in feature code that the reuse-candidates report shows other
  call sites (or concrete planned work) also need → promote it to the canonical
  shared module, named and typed for both callers.
- Almost-general code with one caller's assumptions baked in (hardcoded paths,
  feature-specific types in an otherwise generic function) → make the small
  generalization now, while it's cheap.
- But respect YAGNI: one call site and no concrete second consumer → leave it
  where it is. Speculative generality is a finding in the other direction.

### Structure and design

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

### File and project layout

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

## Axis 3: Style

AI slop a careful author wouldn't have written, and breaks from the codebase's
own conventions.

### AI slop

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

### Convention

Judge against the local codebase's conventions (the docs-and-conventions
report), not personal taste. Flag egregious violations, not preferences:

- Convention breaks: naming, error-handling, typing, or module-layout patterns
  that contradict what the surrounding code and the repo's agent/style docs
  establish.
- Anything a linter or CI already catches is not a finding — drop it.

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

Adversarially check each candidate, with the most effort on bugs:

- **Bugs** (every severity) get three independent skeptics — one traces
  whether the triggering input really reaches the line, one checks whether the
  behavior is intentional (description, history, comments, docs), one looks
  for a guard elsewhere (a caller, a type, a framework). A high or medium bug
  also gets a repro attempt: a scratch worktree at the PR head running the
  narrowest test or a small repro. A reproduced bug always survives; otherwise
  it dies if a majority of the skeptics and a failed repro refute it. Skeptics
  that uphold a bug also re-rate its severity (downgrading non-blockers; the
  median rating wins) and offer a simpler fix when the proposed one
  overcomplicates the code. Keep only with a concrete triggering input or
  sequence.
- **Simplification and structure** findings get two defenders arguing for the
  current code — one names behavior the replacement would lose (callers,
  runtime paths, tests), one names a requirement for it (description, ticket,
  AGENTS.md, roadmap) — and die if either makes its case with concrete
  evidence. Keep only with the replacement, existing code, or destination
  cited by `file:line`, and a payoff that exceeds the churn.
- **Style** findings get one skeptic. Keep slop only if removal leaves the PR
  strictly better, and convention breaks only when egregious.

Drop duplicates of existing review comments. A short list of real findings
beats a long list of maybes.

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
   - **Axis**: bug (high/medium/low), simplification, or style
   - **Why**: bug → triggering scenario, and the repro result if one ran
     (and any out-of-diff file the fix needs);
     simplification → what replaces the component, the existing code to
     reuse, the simpler shape, or the file/config destination; style → what
     a careful human would have written, or the convention broken
   - **Fix**: concrete and minimal — a plain-text diff for bugs; prefer the
     verifiers' simpler fix when one was offered
2. Order findings bugs → simplification → style, by severity. Don't flood
   style nits when bugs or structural issues exist.
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
