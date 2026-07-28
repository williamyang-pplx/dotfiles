---
name: pr-description
description: Write a PR description in William's preferred structure — four sections (Motivation, Changes, Testing, Rollout) as short human-sounding bullets. Use when asked to write, draft, or clean up a pull request description. When updating an existing description, treats any diff from prior model-written text as a human edit and never overwrites it — deletions stay deleted, rewording stays as the human wrote it.
---

# Write a PR description

Draft a pull request description from the change under review (the current
diff, a named branch, or a PR the user points to). Read the diff first so the
content is grounded in what actually changed — never invent work that isn't
there.

## Structure

When there isn't a repo specified PR template, always use exactly these four sections, in this order:

1. **Motivation** — why this change exists: the problem, bug, or goal.
2. **Changes** — what the diff actually does.
3. **Testing** — how it was verified (tests added/run, manual checks). If it
   wasn't tested, say so plainly.
4. **Rollout** — anything needed to ship safely: flags, migrations, config,
   sequencing, backout plan. Write "Nothing special" if there's truly nothing.

Keep the section headings even when a section is thin — a one-line answer under
a heading beats dropping the heading.

## Updating an existing description: never overwrite human edits

When the PR already has a description, read it before writing and diff it
against what the assistant last wrote (an earlier draft from this session, or
the shape/voice above as a tell for agent-written text). **Any difference
from what the model previously wrote is a human edit — deletions, rewording,
reordering, or added text — and human edits are immutable.** Write around
them, never over them:

- **Deleted sections or bullets stay deleted.** Don't re-add them or re-cover
  their content elsewhere, even if the structure above calls for them — the
  "always four sections" rule applies to fresh drafts only. Restore a cut
  section only if the user explicitly asks.
- **Reworded text keeps the human's wording.** Don't "improve" it back toward
  the drafted phrasing or the voice rules, even when updating the bullet
  right next to it.
- **Human-added content stays verbatim** and stays where the human put it.
- New information (e.g. fresh commits to summarize) goes in as *additions* to
  the relevant section — append or insert new bullets rather than rewriting
  existing ones. Only replace an existing line when it's provably still the
  assistant's own untouched text and it's now factually wrong.
- Confine the update to what was asked and leave everything else
  byte-for-byte alone.
- When unsure whether text is the human's or the model's, treat it as the
  human's. A description that matches the four-section shape but lacks one
  section is a deliberate trim — leave it out. A free-form description that
  never had the shape is a fresh-draft candidate; confirm before
  restructuring it.

- Keep PR descriptions to 4 bullet points max. Reviewers should be able to read the description in under a minute.
- **Short bullets, not paragraphs.** Each bullet is one point and max one sentence long.  
- **Sound like a human wrote it.** Plain, direct language. Avoid usinng unnecessary commas, semicolons, or colons. 
- **Cut the filler.** No "This PR aims to...", "In order to...", "It is worth
  noting that...", "Additionally, we have...". Say the thing.
- **Don't restate the diff line by line** — summarize intent, not every hunk.
- **Avoid overusing a lot of fancy formatting** such as `file_name`	or `class name` 
in the description.

## Example shape

```
## Motivation
- Scheduler dropped requests when all backends were draining.

## Changes
- Retry against the next healthy backend instead of failing fast.
- Cap retries at 3 to avoid thundering-herd on a full outage.

## Testing
- Ran unit tests and everything passed. 
- Ran the scheduler soak test locally, no dropped requests.

## Rollout
- Nothing special — behavior only changes on the drain path.
```

For the tests section you should never mention running lints or formatting
as an example of running a test.
