---
name: linear-ticket
description: Solve a Linear ticket end-to-end — always starts in plan mode, reads the ticket and the prior code changes its task depends on, presents a detailed file/class/function-level implementation plan for user approval, then implements the fix. Use when asked to tackle, pick up, work on, or solve a Linear ticket/issue (e.g. "tackle AI-9586", "work on this Linear ticket"). Always runs with the strongest available models.
---

# Tackle a Linear ticket

Take a Linear ticket from a clean main to a working implementation. Move
deliberately: understand the ticket and the code it builds on before writing
anything. This is a coding workflow — obey the repo's `AGENTS.md`/`CLAUDE.md`
conventions throughout.

## 0. ALWAYS start in plan mode

Before doing anything else, enter plan mode (`EnterPlanMode`). This is
unconditional — even for tickets that look like one-liners. Steps 1–3 below
(reading the ticket and exploring the code) happen inside plan mode and are
read-only; no code is written, no worktree is created, and no branch is
touched until the user has approved a plan.

The plan you present must be a detailed, implementation-level design, not a
sketch. It must spell out:

* every file you will create or modify, by path;
* every class, function, and method you will add or change in each file,
  with names and (for new ones) rough signatures;
* how the new code connects to the existing primitives found in step 3;
* the tests you will add or update, and the Bazel targets you will run to
  validate.

Present this plan via `ExitPlanMode` and wait for the user's approval. If
they push back, revise and present again — never proceed to steps 4–5 on an
unapproved plan.

## Use the strongest models

This workflow is invoked when correctness matters most. Run the main loop
with the strongest available model and high reasoning effort. If the current
session is not on the strongest model, say so up front so the user can switch.

Sub-agents, however, should favor speed. When you dispatch sub-agents for
exploration or planning, launch them with `model: opus` and `effort: 'high'`
(not `xhigh`/`max`), and keep their scope tight so they return quickly — run
them in parallel whenever the work is independent rather than serially. On
Codex, likewise prefer fast, tightly-scoped sub-agents over deep, slow ones.

## 1. Sync main

Every ticket is worked in its own dedicated worktree — never branch or switch
branches in the user's current checkout.

During plan mode, only fetch so the history you explore is current:
`git fetch origin`. Note whether a PR branch already exists for this ticket,
but defer everything that mutates the checkout — pulling main, creating
worktrees, rebasing — until after the plan is approved.

Once the plan is approved, get main current before creating the worktree:

1. Update the local default branch: if the current worktree has main checked
   out, `git pull --ff-only`; otherwise `git fetch origin main:main`. If main
   cannot fast-forward, surface the problem and stop.
2. If a PR branch already exists for this ticket, put it in its own worktree
   now: `git worktree add ../<repo>-<ticket-key> <branch>` (if the branch is
   already checked out in another worktree, use that one — git only allows a
   branch in one worktree). Inside that worktree, rebase onto the freshly
   synced main (`git rebase main`) before making any code changes. If the
   rebase hits conflicts, stop immediately — do not resolve, `--abort`, or
   `--continue` yourself. Conflicts are handled manually by the user; tell
   them what conflicted and wait.

Otherwise do not create the worktree yet — create it in step 4 once you
understand the task, so the branch name reflects the ticket.

## 2. Read the ticket

Identify the ticket from the argument (e.g. `AI-9586`) or the current branch.
Then read it in full with the Linear MCP:

1. `mcp__linear__get_issue` for the title, description, status, assignee,
   labels, parent, and linked project/milestone.
2. `mcp__linear__list_comments` for discussion, decisions, and scope changes
   that the description alone won't show.
3. Note any linked issues, sub-issues, parent epics, or referenced PRs/docs —
   these define scope and dependencies. Fetch the ones the task depends on.

Extract the concrete acceptance criteria. If the ticket is ambiguous,
underspecified, or looks larger than a single change, ask clarifying
questions before writing code rather than guessing.

## 3. Explore the code the task depends on

Tickets rarely stand alone — they extend or follow prior work. Build that
context before designing a solution:

1. From the ticket, identify the milestone/epic and its sibling tickets. In
   this monorepo commits are tagged (e.g. `[M1-T5] ... (AI-9586)`); use
   `git log --oneline --grep` on the ticket key, milestone tag, or feature
   name to find the PRs this task builds on.
2. Read those prior diffs (`git show <sha>`) to learn the established
   patterns, primitives, and file layout the new work must fit into.
3. Locate the modules the ticket touches and read enough surrounding code —
   callers, callees, types, tests — to implement in the existing style.

For a broad or unfamiliar area, dispatch an `Explore` sub-agent (`model: opus`,
`effort: 'high'`, tightly scoped for a fast return) to map the relevant files
and conventions, and keep the conclusion.

With this context in hand, write the detailed implementation plan described
in step 0 — files, classes, functions, tests — tied to the ticket's
acceptance criteria. For a non-trivial change, use the `Plan` agent
(`model: opus`, `effort: 'high'`, tightly scoped) to pressure-test the
approach first. Then present the plan with `ExitPlanMode` and wait for
approval.

## 4. Solve the ticket

Only after the user has approved the plan:

1. Do the sync-main and existing-branch steps deferred from step 1.
2. Create a dedicated worktree with a fresh feature branch named for the
   ticket: `git worktree add ../<repo>-<ticket-key> -b ai-9586-<slug> main`.
   Do all implementation, testing, and linting inside this worktree; leave
   the user's original checkout untouched, and leave the worktree in place
   when done — the user removes it after the PR lands.
3. Implement the approved plan — the files, classes, and functions the user
   signed off on — following the codebase's patterns and the Python/Rust
   guidelines in `AGENTS.md`. Reuse the primitives you found in step 3
   instead of reinventing them. If implementation reveals the plan was wrong
   in a way that changes its shape, stop and re-plan with the user rather
   than silently diverging.
4. Validate: run the relevant tests (`bazel test //...` for the touched
   targets) and the `linting` skill (ruff, pylint, ty, rustfmt, clippy,
   buildifier) before considering the work done.
5. Commit the work, push the branch, and open the PR **as a draft**
   (`gh pr create --draft`). Every PR starts in draft mode — the user decides
   when to mark it ready for review. Use the `pr-description` skill for the
   description. The first push of this fresh branch is a plain
   `git push -u origin <branch>` — /push-stacked-pr isn't needed (nothing is
   stacked above a new branch) and its submit step would open the PR itself,
   bypassing the draft rule. But rebase onto latest `origin/main` before that
   first push if main has moved since branching, and any **later** push to
   this PR (follow-up fixes, review feedback) goes through the
   /push-stacked-pr skill so the branch and anything stacked on it by then
   stay rebased and pushed together.
6. Report what you changed against the ticket's acceptance criteria, note any
   criteria you could not meet and why, and state the worktree path, branch,
   and draft PR link.

Never respond to comments on the Linear ticket directly — no replies,
comments, or status updates posted to Linear, even to answer a question
asked there. Surface anything that needs a response to the user and let
them handle Linear communication themselves.
