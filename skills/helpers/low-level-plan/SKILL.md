---
name: low-level-plan
description: Expand an existing high-level plan into a low-level implementation plan — code-skeleton outlines of every file, class, method, function signature, and config field to be added or changed, written as they will actually appear in the files — and present it in plan mode for the user to comment on. Use when asked for a low-level plan, a detailed/implementation-level design, or to flesh out, drill into, or make concrete a high-level plan that already exists (e.g. "/low-level-plan", "now give me the low-level version of this plan"). Read-only: it designs and presents, never implements.
---

# Low-level plan from a high-level plan

The input is a plan that already exists — usually one written earlier in this
session. The output is the same plan at implementation altitude: every file
touched, every function/class/method signature added or changed, every config
field — laid out as code skeletons that read like the future files, so the
user can review the design **before** any code is written.

This skill never implements. It ends when the user has an approved low-level
plan; the implementation is a separate, explicitly-requested step.

## 0. ALWAYS work in plan mode

Enter plan mode (`EnterPlanMode`) before anything else — unconditionally, even
when the high-level plan looks small. Everything below is read-only: no files
written, no branches or worktrees created. Present the finished low-level plan
with `ExitPlanMode` and wait for the user.

## 1. Find the high-level plan

In order of preference:

1. The plan produced or approved earlier in this session — the usual trigger.
2. A plan the user points at: a message, a file (often under
   `~/Documents/llm-plan-docs/claude-plans/`), a Linear ticket, a PR
   description.

Read it in full and restate, in two or three lines, the goal and scope you are
working from. Never invent a high-level plan to expand: if there isn't one, say
so and offer to write one first.

## 2. Ground the plan in the actual code

A high-level plan is allowed to be vague or slightly wrong about the codebase;
a low-level plan is not. Before designing anything, verify every claim the
high-level plan makes about existing code:

1. Read the files and modules it names — plus their callers, callees, types,
   and tests — so new code matches the surrounding style.
2. Locate the primitives to reuse: existing helpers, base classes, config
   objects, error types, test fixtures. Reuse beats new code, and the user
   should see in the plan which existing thing each new piece hangs off.
3. Check the repo's `AGENTS.md`/`CLAUDE.md` and the local conventions for the
   language in play — naming, typing, error handling, module layout.
4. Flag anything in the high-level plan that the code contradicts (a function
   that doesn't exist, a layer that already does the work, an assumption that
   no longer holds). These go in the plan's "Deviations" section, not silently
   into the design.

For a broad or unfamiliar area, dispatch `Explore` sub-agents — tightly scoped,
in parallel when the work is independent — and keep the conclusions. Only spawn
sub-agents if the user has not asked you to avoid them.

## 3. Write the low-level plan

Cover the whole change, file by file, as **code skeletons**: for each file, a
code block in the target language showing the file's planned shape exactly as
it will read once implemented — declarations in the order they will appear in
the file, real syntax, real names, real types. Not bullet points describing
code ideas; a reviewer should be able to squint at the skeleton and see the
future file. Give every item a short stable ID (`F1`, `C2`, `K3`, …) — as a
comment on the declaration — so the user can comment by reference instead of
quoting.

Include, wherever it applies:

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
  compatibility windows, flag defaults, ordering constraints.
* **Deviations from the high-level plan** — what you are doing differently and
  why, from step 2's findings.
* **Open questions** — the decisions you want the user to make, each with your
  recommended answer so silence still leaves a workable plan.

Suggested shape:

```markdown
## Summary
<2–3 lines: what gets built, at what altitude, against which high-level plan>

## path/to/file.py  [modify]

```python
def resolve_target(cfg: TargetConfig, *, strict: bool = False) -> Target | None:  # F1
    """Resolve a config entry to a live target."""
    # look up cfg.name in the existing TARGET_REGISTRY (reused, not new)
    # on miss: raise UnknownTargetError if strict, else return None


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
```

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

## 4. Present it and iterate

Present the plan with `ExitPlanMode` and stop. When the user comments, revise
the affected items — keeping the IDs stable so the conversation stays anchored
— and present again. Do not start implementing on an unapproved plan, and do
not treat "looks good" on one section as approval of the rest.

If the plan is worth keeping past this conversation, offer the `save-plan`
skill once it's approved.
