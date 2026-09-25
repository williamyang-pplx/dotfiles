---
name: shorten-pr-description
description: Rewrite a pull request's description to be short and scannable — at most 150 words, bulleted summary, and no Testing or Reviewer Notes sections unless the user asks to keep them. Use when asked to shorten, trim, tighten, or condense a PR description. Also invoked automatically as the final pass by skills that write or update PR descriptions (pr-authoring and its callers).
---

# Shorten a PR description

Rewrite an existing PR's description down to something a reviewer can read
in one glance. Do not touch the code, the title, or anything else about the
PR — only the body.

## Gather

1. Identify the PR (argument, current branch via `gh pr view`, or ask).
2. Fetch the current body: `gh pr view <pr> --json body,title`.
3. Skim the diff stat (`gh pr diff <pr> --stat`) only if the existing
   description is too thin or vague to rewrite from — the diff is for
   accuracy, not for adding new material.

## Write with simple-english

Invoke the `simple-english` skill in pragmatic mode before drafting, and keep
it on for the whole rewrite. It owns the sentence: 20/25-word limits, one word
one meaning, simple tenses, active voice, no filler. This skill owns the
length and the structure; where they disagree, this one wins. Code, commands,
identifiers, and diagrams are untouchable in both skills.

## Rewrite rules

- **Hard cap: 150 words** for the entire body. Count them; if over, cut
  detail, not clarity.
- **Summary as bullets.** Lead with one plain sentence saying what the PR
  does and why, then a short bullet list of the concrete changes. No
  paragraph-form summaries.
- **Drop Testing and Reviewer Notes sections** (and equivalents like "Test
  plan" or "Notes for reviewers") unless the user explicitly says to keep
  them. If one of those sections contains something load-bearing — a known
  limitation, a migration step, a follow-up PR — fold that single fact into
  a bullet rather than keeping the section.
- Preserve anything structural the repo relies on: ticket links, magic
  strings for automation, `🤖 Generated with...` footers, and stack
  markers (e.g. gh-stack's stack table). These do not count toward the
  150 words.
- Keep the author's claims as-is; shortening is not the time to invent new
  descriptions of behavior you haven't verified.

## When invoked from another skill

Skills that author or update PR descriptions (`pr-authoring`, and callers
like linear-ticket, e2e-test, address-pr-comments, format-code) invoke this
skill as their final pass. In that case, two exceptions to the rules above:

- **Keep the repo template's required headings** (e.g. Description, Testing
  Strategy, AI Usage, Reviewer Notes). Shorten the content under each; leave
  a heading empty rather than delete it. Empty headings and diagrams do not
  count toward the 150 words.
- **Never cut content the invoking skill just added.** If e2e-test just
  recorded a run under Testing Strategy, that bullet stays verbatim.

Everything else — the 150-word cap on prose, bullets over paragraphs,
simple-english — applies unchanged.

## Apply

Show the rewritten body, then update it with
`gh pr edit <pr> --body <new-body>`. If the user asked only for a draft,
stop after showing it.
