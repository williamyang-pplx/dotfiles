---
name: address-pr-comments
description: Respond to review comments on a pull request. Use when asked to reply to, address, or handle PR comments. Bot/agent comments (pplx-bot, Copilot, AI reviewers) are verified against the wider codebase before their claims are acted on. AI may reply directly to AI/bot-generated comments and to William's own comments (williamyang-pplx), but must never post AI-generated replies to other human comments without permission — draft those for William to review and send himself.
---

# Respond to PR comments

Work through the review comments on a pull request: read each comment thread,
make any code changes it calls for, and handle the reply according to who wrote
the comment.

## The rule: who wrote the comment decides who replies

- **AI/bot comments** (e.g. GitHub bots, automated code-review agents, Copilot,
  Claude-based reviewers — anything with a `[bot]` account or clearly
  machine-generated): you may respond directly with AI-generated text. Post the
  reply yourself.
- **William's own comments** (GitHub user `williamyang-pplx`): that's William —
  you may respond directly, same as bot comments. These are typically notes or
  instructions to the agent; do the work and reply.
- **Other human comments**: never respond with AI-generated text without
  permission. Do not post a reply on William's behalf. Instead, address the
  substance (make the code change, investigate the question) and present a
  suggested reply to William in the conversation so he can write or send the
  response himself.

When authorship is ambiguous, treat the comment as another human.

## Verify bot/agent claims before acting on them

Bot and agent reviewers (`pplx-bot`, Copilot, Claude-based reviewers, any
`[bot]` account) see a narrow slice of the diff and regularly assert things
that are wrong in the wider codebase. Never take their claim at face value and
never apply their suggested patch as-written just because it was suggested.

For every bot/agent comment, before you change any code:

1. Read the actual code the comment points at, plus enough surrounding
   context to judge it — the whole function, its callers, and the types
   involved. A claim about a "null deref" or "missing await" is only real if
   the call path can actually reach that state.
2. Check the claim against the rest of the repo: grep for other callers,
   existing helpers, established conventions, and tests that already cover
   the case. Bots often flag intentional patterns or propose duplicating
   something that already exists.
3. Confirm the suggested fix is correct *and* better. A bot can be right that
   something is broken and wrong about how to fix it. Prefer the fix that
   matches the codebase's conventions over the bot's literal diff.
4. Decide explicitly: **valid** (fix it), **valid but wrong fix** (fix it your
   way, say so in the reply), or **false positive** (change nothing).
5. If the claim can't be settled from the code — it depends on runtime
   behavior, external services, or intent you can't recover — say so rather
   than guessing. Do not make a speculative change to satisfy a bot.

Spend the verification effort proportional to the change the bot is asking
for: a rename needs a glance, a claimed correctness bug or a suggested
refactor of shared code needs real investigation.

State the verdict for each bot comment in your summary to William, with the
evidence (file:line, the caller you checked) that supports it. For false
positives, reply with the one-sentence reason and resolve nothing you aren't
sure about.

## Workflow

1. Fetch the open review threads with `gh` (e.g.
   `gh pr view --comments`, or the API for inline review threads).
2. Classify each thread's author: bot, William (`williamyang-pplx`), or
   other human.
3. Before making any code changes, pull the latest main and rebase the PR
   branch onto it (`git fetch origin main && git rebase origin/main`). If the
   rebase hits conflicts, stop immediately — do not resolve, `--abort`, or
   `--continue` yourself. Conflicts are handled manually by the user; tell
   them what conflicted and wait.
4. For each bot/agent thread, run the verification above and reach a verdict
   before touching the code.
5. For each comment, do the underlying work first — fix the code, answer the
   question with evidence from the repo — before writing any reply.
6. Push any code changes by invoking the /push-stacked-pr skill with this PR
   as the bottom of the stack — never a plain `git push`. It rebases the
   branch onto main, restacks every branch stacked above it, and pushes the
   whole stack with gh stack's safety checks.
7. Bot and williamyang-pplx threads: post a concise reply (and resolve the
   thread if the fix is pushed).
8. Other human threads: summarize the thread and your proposed response back
   to William; let him reply.
9. If any code changes were pushed, automatically update the PR description:
   invoke the /pr-authoring skill at the end so the description reflects
   the updated diff.

## Reply voice

- Short and plain — one or two sentences per reply.
- Reference the fix concretely ("Fixed in <commit sha>", "Renamed in the latest
  push") rather than restating the whole change.
- Don't argue with bots at length; if a bot finding is a false positive, say
  why in one sentence and move on.
