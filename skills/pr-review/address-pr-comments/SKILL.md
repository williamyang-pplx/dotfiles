---
name: address-pr-comments
description: Respond to review comments on a pull request. Use when asked to reply to, address, or handle PR comments. AI may reply directly to AI/bot-generated comments and to William's own comments (williamyang-pplx), but must never post AI-generated replies to other human comments without permission — draft those for William to review and send himself.
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
4. For each comment, do the underlying work first — fix the code, answer the
   question with evidence from the repo — before writing any reply.
5. Push any code changes by invoking the /push-stacked-pr skill with this PR
   as the bottom of the stack — never a plain `git push`. It rebases the
   branch onto main, restacks every branch stacked above it, and pushes the
   whole stack with gh stack's safety checks.
6. Bot and williamyang-pplx threads: post a concise reply (and resolve the
   thread if the fix is pushed).
7. Other human threads: summarize the thread and your proposed response back
   to William; let him reply.
8. If any code changes were pushed, automatically update the PR description:
   invoke the /pr-description skill at the end so the description reflects
   the updated diff.

## Reply voice

- Short and plain — one or two sentences per reply.
- Reference the fix concretely ("Fixed in <commit sha>", "Renamed in the latest
  push") rather than restating the whole change.
- Don't argue with bots at length; if a bot finding is a false positive, say
  why in one sentence and move on.
