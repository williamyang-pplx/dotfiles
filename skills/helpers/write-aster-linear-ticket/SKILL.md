---
name: write-aster-linear-ticket
description: Write a new Linear ticket for the Aster project — captures the ask as a high-level, intentionally-broad ticket that points at the design direction and the files it might touch, without prescribing low-level design. Use when asked to write, draft, file, or open an Aster ticket/issue (e.g. "write an Aster ticket for X", "file this under Aster"). Always creates the ticket under the Aster project on the AI team, assigned to William Yang, in Todo by default.
---

# Write an Aster Linear ticket

Turn a request into a well-scoped Linear ticket filed under the **Aster**
project. The whole point of these tickets is to set direction, not to design
the solution — they say *what* we want and *roughly where* it lives, and leave
the *how* to whoever picks the ticket up (often the /linear-ticket workflow,
which starts by designing an implementation plan from scratch).

## The one rule that matters: stay high-level

Every Aster ticket uses **broad language**. Never bake in low-level design
decisions — no function signatures, no class layouts, no data-structure
choices, no line-level algorithms. Prescribing the implementation defeats the
purpose and boxes in the person who solves it.

Instead a ticket gives:

* **The intent** — what outcome or capability we want, and why it matters.
* **High-level design pointers** — the *direction* we're leaning (e.g. "extend
  the existing gateway rather than adding a new service", "reuse the caching
  layer already in place"), phrased as guidance, not a spec. If we genuinely
  don't have a preference, say so and let the implementer decide.
* **File / area pointers** — the modules, packages, or files where this would
  *potentially* be implemented, so the solver knows where to start looking.
  Always frame these as candidate starting points ("likely lives around
  `path/to/file.py`", "see the primitives in `pkg/foo/`"), never as a
  mandate.

If you catch yourself writing pseudocode or naming specific functions to add,
you've gone too deep — pull back up to intent and pointers.

## 1. Understand the ask

Get the ticket's substance from the user's request and this conversation.
Before writing, make sure you can answer:

* What do we actually want, in one or two plain sentences?
* Why — what problem or opportunity does it address?
* What's the rough design direction, if we have one?
* Which files or areas of the codebase would this plausibly touch?

If any of these is unclear and you can't reasonably infer it, ask the user a
short clarifying question rather than guessing. To find file/area pointers you
aren't sure about, explore the codebase read-only (search, read) or dispatch an
`Explore` sub-agent — but only to *locate candidate files*, not to design the
fix. Keep those pointers as hints.

## 2. Draft the ticket

**Title**: a short, outcome-oriented summary — what we want, not how.

**Description** (Markdown, use literal newlines — the Linear MCP wants real
newlines, not `\n`): keep it broad and skimmable. A good shape:

```markdown
## Goal
<1–2 sentences: what we want and why.>

## Direction
<High-level design pointers phrased as guidance. What approach we're leaning
toward and why, or an explicit "implementer's choice" where we have no
preference. No low-level design.>

## Where this likely lives
<Candidate files / modules / packages as starting points, each with a word on
what's there. Framed as pointers, not a mandate.>

## Notes / open questions
<Optional: context, links, dependencies, things to figure out during design.>
```

Drop any section that has nothing real to say — don't pad. Prefer plain,
human-sounding bullets over dense prose.

## 3. Create it in Linear

Create the issue with `mcp__linear__save_issue`, always with these fixed
values for Aster:

* `team`: `AI`
* `project`: `Aster`
* `state`: `Todo`  ← default for every Aster ticket unless the user specifies
  a different state (e.g. explicitly asks for Backlog)
* `assignee`: `William Yang`  ← default assignee for every Aster ticket
  unless the user explicitly asks for someone else or no assignee
* `title` and `description` from step 2.

Do **not** set a priority or estimate unless the user explicitly asks. (For
reference, the Aster project id is `555d92f9-fa04-47d8-9ed4-18238a0c8602` and
it sits on the AI team; passing the names above resolves to these.)

Before creating, if the user asked for several tickets, draft them all and show
the drafts for a quick look before filing — it's cheap to fix a title or
pointer before the issue exists.

## 4. Report

Give the user the created issue's key (e.g. `AI-1234`) and URL, and a one-line
recap of each ticket's goal. If you asked no clarifying questions but made
assumptions to fill gaps, note them so the user can correct the ticket.

Never post comments or status updates on the ticket beyond creating it, and
never respond to Linear comments on the user's behalf — surface anything that
needs a reply to the user.
