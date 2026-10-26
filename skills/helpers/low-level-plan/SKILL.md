---
name: low-level-plan
description: Expand an existing high-level plan into a low-level implementation plan — code-skeleton outlines of every file, class, method, function signature, and config field to be added or changed, written as they will actually appear in the files — grounded by helper scripts that map the code, its callers and co-changed files, docs, and the review comments people left on past PRs in that area, built with the user through explicit decision checkpoints, and gated by a mechanical plan check before it is presented in plan mode. Use when asked for a low-level plan, a detailed/implementation-level design, or to flesh out, drill into, or make concrete a high-level plan that already exists (e.g. "/low-level-plan", "now give me the low-level version of this plan"). Read-only: it designs and presents, never implements.
---

# Low-level plan from a high-level plan

The input is a plan that already exists — usually one written earlier in this
session. The output is the same plan at implementation altitude: every file
touched, every function/class/method signature added or changed, every config
field — laid out as code skeletons that read like the future files, so the
user can review the design **before** any code is written.

This skill never implements. It ends when the user has an approved low-level
plan; the implementation is a separate, explicitly-requested step.

It is the user's design. Ask them about every real fork rather than picking
one quietly, record each answer, and keep their answers settled. Scripts do
the finding; your judgment and the user's decisions handle what the scripts
enumerate.

## Helper scripts

Run `<this skill's base directory>/scripts/llp.py` from inside the target repo.
Each command takes seconds; re-run them freely.

| Command | What it does |
|---|---|
| `llp.py context --area NAME=PATH[,PATH...] … [--plan-file F]` | Gathers the planning context and prints a digest pointing into it (10–30 s). |
| `llp.py outline PATH…` | Symbol outline of files or dirs, at `file:line`. |
| `llp.py callers SYMBOL [--in FILE]` | Where a symbol is used; with `--in`, only files that import FILE. |
| `llp.py threads PATH --ctx DIR [--reviewer LOGIN]` | Past human review threads on a path, with the code each was left on. |
| `llp.py check PLAN.md --ctx DIR [--resolutions FILE]` | Sweeps the plan; exits 0 only when clean (step 5). |

`context` writes `<git-common-dir>/low-level-plan/<head>-<hash>/`:

- `areas/<name>.md` — every file in the area with its line count and symbol
  outline; files outside the area that import it; files that historically
  change in the same commits; the most-churned files; the test landscape
  (test files, Bazel test targets, fixtures, CI configs).
- `docs.md` — the AGENTS.md/CLAUDE.md, README, and OWNERS chain on the touched
  paths, inlined; other docs and lint configs, listed.
- `prs/<number>.md` — each merged or open PR behind the area's recent commits
  that has human review threads, each thread with the diff hunk it was left on
  and whether the code changed afterward.
- `profiles/<login>.md` — the area's top reviewers' comments across the repo.
- `history.md` — open PRs on the same paths, Linear ticket IDs, reviewers,
  owners, recent commits.
- `context.json` — what `check` and `threads` read back.

## 0. ALWAYS work in plan mode

Enter plan mode (`EnterPlanMode`) before anything else — unconditionally, even
when the high-level plan looks small. Everything below is read-only: no repo
files written, no branches or worktrees created. The scripts write only scratch
files under `<git-common-dir>/low-level-plan/` and the resolutions file under
`/tmp/`, which is fine in plan mode. Present the finished low-level plan with
`ExitPlanMode` and wait for the user.

If the user names a plan file to write instead (e.g. a kitchen `.kitchen/plan.md`),
write and revise the plan there and skip plan mode — plan mode blocks that write.
Either way, the draft lives in a file from step 4 on — the named file, or in
plan mode the plan file Claude Code provides — so `check` and the reviewers
read it from there.

## 1. Find the plan and scope it with the user

In order of preference:

1. The plan produced or approved earlier in this session — the usual trigger.
2. A plan the user points at: a message, a file (often under
   `~/Documents/llm-plan-docs/claude-plans/`), a Linear ticket, a PR
   description.

Read it in full and restate, in two or three lines, the goal and scope you are
working from. Never invent a high-level plan to expand: if there isn't one, say
so and offer to write one first.

Then split the code the plan touches into **areas** — independent modules, file
groups, or cross-cutting concerns like config, wiring, or tests — capped at ~6.
Each area is a name plus repo-relative paths (files or dirs; planned new files
are fine).

Before gathering context, ask the user (`AskUserQuestion`) whatever could change
the scope or the areas: goals and non-goals, how far the change should go,
compatibility constraints, and whether the area split is right. Ask only what
the plan leaves open, not what the code will answer. Answers that change scope
go into the plan's **Decisions** from the start.

## 2. Gather context

1. Write the high-level plan to `/tmp/llp-plan-<slug>.md` and run
   `llp.py context --area … --plan-file /tmp/llp-plan-<slug>.md`. The digest names
   each area's top importers and co-changed files, the PRs and reviewers mined,
   open PRs on the same paths, tickets, and any warnings (e.g. no GitHub
   remote means no PR history). Tell the user about warnings.
2. Read `docs.md`, `history.md`, and the `areas/*.md` of the areas central to the
   design, then the source files the plan extends. Use `outline`, `callers`, and
   `threads` to drill in instead of broad searches.
3. Read the review history: the `prs/` threads on the files the plan touches,
   and the `profiles/`. Turn the lasting preferences into **Conventions** rules,
   each specific and imperative ("Do X, not Y") with evidence (`#123 @reviewer
   path:line`). A rule raised on two or more PRs, or by two reviewers, is
   strong; keep a one-off only if a reviewer insisted or the author changed the
   code because of it. A thread marked "code changed after" was usually acted on.
4. If tickets are listed and the Linear tools are available, read the tickets
   the plan references, then those of the area's recent PRs, one hop out.
   Record the decisions and scope cuts they hold.

For a large plan, read in parallel: in ONE message, dispatch read-only
`Explore` agents (`model: "sonnet"`) with the `Agent` tool, one per area,
capped at ~6. Give each the high-level plan, its `areas/<name>.md` path, and
the context dir. Each returns a compact list of items, each with `file:line`:
the signatures the plan extends, reuse targets, importers and co-changed files
the plan must touch, local conventions, and every claim in the plan the code
contradicts. Read the one or two central files yourself while they run.

## 3. Decide with the user

Grounding turns up forks the high-level plan didn't settle: claims the code
contradicts, two workable shapes for the same piece, open PRs to sequence
with, conventions that cut against the plan, scope the code says is missing.
Ask the user about each one with `AskUserQuestion` — up to 4 questions per
call, your recommended option first and labelled, and a `preview` with the
competing skeletons when the choice is about code shape. Don't ask what the
code or the docs already answer.

Record every answer in **Decisions** (`D1`, `D2`, …) with the item IDs it
shapes. Decisions are settled: later steps build on them, reviewers don't
re-litigate them, and only a correctness bug reopens one — as a new question
to the user.

## 4. Write the low-level plan

Write the plan into the plan file following the skeleton rules below.

When it spans more than ~4 files, write the **contract** first: Summary,
Decisions, Conventions, the file list with [new]/[modify]/[delete] labels,
every ID, and every signature or schema that crosses a file boundary. Show it
to the user and ask whether the shape is right before writing the skeletons.
Then write the skeletons yourself, or, for a very large plan, dispatch one
`general-purpose` drafter per file group in ONE message with the contract
path and the skeleton rules, and stitch their sections in reviewer order,
fixing any drift from the contract.

### Skeleton rules

Cover the whole change, file by file, as **code skeletons**: for each file, a
code block in the target language showing the file's planned shape exactly as
it will read once implemented — declarations in the order they will appear in
the file, real syntax, real names, real types. Not bullet points describing
code ideas; a reviewer should be able to squint at the skeleton and see the
future file. Give every item a short stable ID (`F1`, `C2`, `K3`, …) — as a
comment on the declaration — so the user can comment by reference instead of
quoting.

Include, wherever it applies:

* **Decisions** — every answer the user gave, as `- **D1** <question> → <answer>`,
  with the item IDs it shaped. Reviewers treat these as settled.
* **Conventions** — the reviewer expectations and documented conventions this
  plan is held to, each with its evidence (`#123 @reviewer`, doc path) and the
  item IDs it shaped. Only rules that bear on this plan; skip what lint enforces.
* **Files** — every path you will add, modify, or delete, each labelled
  `[new]` / `[modify]` / `[delete]`, in the order a reviewer should read them.
  For each, one skeleton code block. In `[modify]` files, show only the parts
  being added or changed, anchored by the real surrounding declarations
  (`class Foo:` … `# unchanged` …) so their position in the file is clear.
* **Functions and methods** — the full `def`/`func`/`fn` line as it will be
  written: name, parameters with types, return type, decorators,
  async/static/classmethod. A docstring (or doc comment) in the house style
  saying what it does, and the body outlined as placeholder comments — one per
  step, covering the calls made and the error cases — in the order the real
  statements will go.
* **Classes** — the real class statement with base classes, field declarations
  with types, and each method skeletoned as above, in file order. Note (in the
  docstring or a comment) what owns the instance and its lifetime.
* **Data models / schemas** — dataclasses, pydantic models, protobufs, DB
  columns, API request/response shapes — written out as the actual
  declarations, with field types and nullability.
* **Configs** — every new or changed field shown as the literal lines that
  will land in the config file (full key path, default), plus a comment giving
  type, units, valid range, and where it is read.
* **Wiring** — how the new pieces are reached from existing entry points:
  the call path, registrations, dependency injection, feature flags, exports.
* **Tests** — the test files and case names you will add or change, what each
  asserts, the fixtures/mocks needed, and the exact commands to run them
  (e.g. the `bazel test` targets).
* **Migration / rollout** — only when the change needs it: backfills,
  compatibility windows, flag defaults, ordering constraints, and any open PR
  on the same paths (`history.md`) that this has to land before or after.
* **Deviations from the high-level plan** — what you are doing differently and
  why, from what grounding found.
* **Open questions** — the decisions you want the user to make, each with your
  recommended answer so silence still leaves a workable plan.

Suggested shape:

````markdown
## Summary
<2–3 lines: what gets built, at what altitude, against which high-level plan>

## Decisions
- **D1** Retry on every storage error, or only transient ones? → only transient
  (`OSError`, timeouts). Shapes F1.

## Conventions
- **V1** Raise `ServiceError` subclasses, never bare `ValueError`, from
  resolver code — #4121 @alice, #4307 @bob. Shapes F1, C2.
- **V2** Tunables live in `configs/service.yaml`, not module constants —
  `src/service/AGENTS.md`. Shapes K3.

## path/to/file.py  [modify]

```python
def resolve_target(cfg: TargetConfig, *, strict: bool = False) -> Target | None:  # F1
    """Resolve a config entry to a live target."""
    # look up cfg.name in the existing TARGET_REGISTRY (reused, not new)
    # on miss: raise UnknownTargetError (V1) if strict, else return None


class TargetResolver(BaseResolver):  # C2
    """Owns the target cache; one instance per process, built in main()."""

    _cache: dict[str, Target]
    _clock: Clock

    def resolve(self, name: str) -> Target:
        # return cached entry if younger than resolver.cache_ttl_seconds (K3)
        # otherwise call resolve_target(strict=True) and cache the result

    def invalidate(self, name: str) -> None:
        # drop name from _cache; no-op if absent
```

## configs/service.yaml  [modify]

```yaml
resolver:
  cache_ttl_seconds: 300  # K3 — int, seconds, 0 disables caching; read by C2.resolve
```

## Tests
- **T4** `tests/test_resolver.py` — cache hit, expiry via fake `Clock`,
  strict-mode raise. Run: `bazel test //service:resolver_test`.

## Deviations
- ...

## Open questions
- ...
````

Depth over breadth of prose: no restating the high-level plan's motivation, no
"considerations" filler. Every line should be something the user can approve or
strike.

**Skeletons, not implementations.** Everything outside the bodies — imports
worth noting, signatures, class statements, field and config declarations —
is written exactly as it will land in the file. The bodies themselves stay as
placeholder comments outlining the steps: real statement-level logic belongs
in the implementation step, since a plan full of finished code can't be
reviewed at the design level and locks in choices the user hasn't agreed to
yet. A real line inside a body is fine only where a comment would be more
ambiguous than the code (a tricky type, a one-line delegation, a config
literal's shape).

## 5. Run the plan check until clean

```
llp.py check <plan file> --ctx <context dir> --resolutions /tmp/llp-resolutions-<slug>.txt
```

1. **Fix every BLOCK.** BLOCKs are never justifiable.
2. **Resolve every WORKSHEET item**: fix the plan, or append a line to the
   resolutions file (never commit it):

   ```
   <item-id> <one-line justification>
   ```

   An empty justification doesn't count. A justification states a fact you
   checked ("sft.py:209 is the only constructor call; added as a Wiring item").
   When an item is a design choice rather than a fact, ask the user and
   resolve it as `<item-id> user: <their answer>`, then add it to Decisions.
3. Re-run until it prints `llp check: clean` (exit 0). Never present a plan
   while it exits non-zero. Re-run it after every revision, too.
4. Carry the surviving justifications into **Deviations** or **Open
   questions**, and the `user:` ones into **Decisions**, so deliberate choices
   read as deliberate.

### Rule catalog

- **S1–S7, Q1 (BLOCK)** — Structure the plan can't be reviewed without.
  - S1: a `## Summary` or `## Tests` section is missing.
  - S2: there are no file sections.
  - S3: a file section has no skeleton.
  - S4: an ID is defined twice.
  - S5: a `[modify]`/`[delete]` path isn't tracked.
  - S6: a `[new]` path already exists.
  - S7: a deleted file is still imported by files the plan never mentions.
  - Q1: an open question has no recommended answer.
- **G1 (anchor)** — A declaration in a `[modify]` skeleton has no ID and isn't
  in the file. Either the anchor's name is wrong, or it's a new item missing
  its ID. Read the file and fix whichever it is.
- **G2 (dangling reference)** — The prose points at an ID nothing defines.
- **T1 (callers)** — The plan changes an existing symbol, and files that import
  its module use it, but the plan never mentions them. A changed constructor is
  checked against the type's callers. Read each caller (`llp.py callers SYMBOL
  --in FILE`). Add the ones that must change as **Wiring** items; justify only
  when the signature and contract really are unchanged.
- **T2 (co-change)** — A touched file has changed together with files the plan
  never mentions, in 3+ commits. That is the wiring plans most often miss:
  registrations, BUILD files, configs, fixtures. Read a shared commit
  (`git log --full-diff -- <file>`) and add what this change needs.
- **R1 (reuse)** — A new symbol's name is already defined elsewhere. Read the
  twin. Reuse it, or say in one line why it doesn't fit.
- **B1 (BUILD)** — A new file lands in a Bazel package whose BUILD file the plan
  never mentions. Add the target change, or justify (e.g. a glob already covers
  it).
- **X1–X2 (tests)** — A test file in Tests doesn't exist and isn't marked new,
  or a Bazel target doesn't exist and its BUILD file isn't in the plan.
- **C1–C2 (conventions)** — A Conventions rule cites no evidence, or past PRs
  have review threads on the area but the plan has no Conventions section.
- **P1 (past reviews)** — A file the plan modifies has human review threads in
  past PRs. Read them (`llp.py threads PATH --ctx DIR`). Carry any rule that
  applies into Conventions, then resolve with what you took from them, or
  "nothing applies: <why>".
- **O1 (open PRs)** — An open PR changes the same files and the plan never
  mentions it. Look at it (`gh pr view N`). How the plan sequences with it is
  the user's call: ask, and resolve as `user: …`.

The check is mechanical: it can't see bugs, bloat, or a wrong design. Step 6
covers those.

## 6. Review adversarially, then triage

Once the check is clean, review the plan in ONE message of parallel read-only
`Explore` agents (`model: "sonnet"`) dispatched with the `Agent` tool, each
pointed at the plan file and the context dir, not pasted:

1. **Correctness** — one per file group, up to ~4. Assume the plan is wrong
   and find where. Check every signature it extends, every caller it claims,
   every config path. Report contradictions with the code, call sites not
   updated, unhandled error paths, and tests that can't catch the failure
   modes.
2. **Interface** — the cross-file seams only: signature mismatches between
   items, wiring and registration gaps, ordering and migration hazards.
3. **Simplify** — bloat: abstractions with one caller, pass-through wrappers,
   knobs nobody asked for, skeletons doing more than the plan and the
   Decisions require.
4. **Conventions** — hold each skeleton to the Conventions section, the agent
   guides in `docs.md`, the threads in `prs/`, and the reviewers in
   `profiles/`. Flag what a reviewer of this area would push back on, citing
   the evidence.

Tell every reviewer that the Decisions section is settled. It may flag a
decision only for a correctness bug. Each finding names the item ID, gives
`file:line` evidence, and proposes replacement text. Skip a pass only when the
user says to.

Triage the findings yourself; a reviewer's proposed fix is a suggestion. Fold
objective fixes straight in: a wrong signature, a missed call site, a
contradicted claim. Bring judgment calls to the user with `AskUserQuestion`:
dropping or adding scope, changing approach, a convention that fights a
Decision, and above all two findings that propose conflicting fixes. Record
the answers in Decisions. A finding you reject needs a stated reason in Open
questions, never a silent drop. Then re-run `check`.

## 7. Present it and iterate

Present the plan with `ExitPlanMode` and stop. When the user comments:

1. Revise the affected items in place, keeping the IDs stable so the
   conversation stays anchored.
2. Record what the user decided in Decisions.
3. Re-run `check` (seconds).
4. Re-review, with step 6's passes, only the sections whose design changed.
5. Present again.

Do not start implementing on an unapproved plan, and do not treat "looks good"
on one section as approval of the rest.

If the plan is worth keeping past this conversation, offer the `save-plan`
skill once it's approved.
