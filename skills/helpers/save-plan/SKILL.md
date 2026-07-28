---
name: save-plan
description: Save the current plan or implementation plan to a timestamped markdown file under ~/Documents/llm-plan-docs/claude-plans/. Use when asked to save, store, write out, or archive a plan (e.g. "save this plan", "store the implementation plan", "write the plan to disk"). Persists the plan the session just produced (or one the user points at) to a dated file and reports the path.
---

# Save a plan to llm-plan-docs

Write the plan this session produced to its own timestamped markdown file under
`~/Documents/llm-plan-docs/claude-plans/`, so it outlives the conversation. This
only persists a plan that already exists — it does not design one. If there's no
plan yet, say so and offer to draft one first rather than inventing content.

## 1. Get the plan content

Use, in order of preference:

1. The plan just approved in plan mode, or the implementation plan written in
   this conversation — that's the usual trigger.
2. A plan the user points at explicitly (a message, a file, pasted text).

Save the plan **verbatim** — the reasoning, file/function-level steps, and
trade-offs already worked out. Don't re-summarize or trim it down; the point is
a faithful record. If the plan lives only in your head as bullet points from a
back-and-forth, assemble it into a coherent document first, then save that.

## 2. Build the filename

- **Slug**: a short kebab-case description of the plan's subject, matching the
  style of the docs already in `~/Documents/llm-plan-docs/misc/`
  (e.g. `chat-template-encoding`, `inference-gateway`). Keep it to a few words.
- **Timestamp**: `date +%Y-%m-%d-%H%M%S` — run it; do not hand-write the value
  (never guess the time). Lead with it so files sort chronologically.
- **Filename**: `<timestamp>-<slug>.md`, e.g.
  `2026-07-26-152422-inference-gateway.md`.

Target directory: `~/Documents/llm-plan-docs/claude-plans/` (expand `~` to an
absolute path for the Write tool). `mkdir -p` it first in case it's missing.

## 3. Write the file

Start the file with a short header, then the plan body:

```markdown
# <Human-readable title>

Saved: <YYYY-MM-DD HH:MM:SS> (via Claude Code)

---

<the plan, verbatim>
```

Use the same timestamp from step 2 in the `Saved:` line. Don't overwrite an
existing file — if the target name somehow already exists, the seconds-level
timestamp should make that near-impossible, but if it does happen, append a
short suffix rather than clobbering.

## 4. Report

Give the user the absolute path of the file written, and its title. Keep it to a
line or two — the plan itself is in the file now.
