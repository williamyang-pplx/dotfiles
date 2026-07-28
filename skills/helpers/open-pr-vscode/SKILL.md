---
name: open-pr-vscode
description: Open a VS Code window on the checkout of the PR branch being worked on in this session. Use when asked to open the PR/branch/worktree in VS Code (e.g. "open this PR in vscode", "open the branch in code"). Finds the worktree where the branch is checked out, creating one if needed, then runs `code` on it.
---

# Open the PR branch in VS Code

Open a VS Code window rooted at the checkout of the PR branch this session is
working on. Never switch branches in the user's current checkout to do it —
if the branch isn't checked out anywhere, give it its own worktree.

## 1. Identify the PR branch

1. `git branch --show-current` in the working directory. If it's a feature
   branch, that's the PR branch.
2. If the current branch is the default branch (main/master), the session is
   probably driving work in another worktree — check `git worktree list` for
   the branch discussed in this conversation, or ask the user which branch
   they mean rather than guessing.

## 2. Find where the branch is checked out

Run `git worktree list --porcelain` and look for a worktree whose `branch`
line matches `refs/heads/<branch>`:

- **Found** (including the current worktree): the path to open is that
  worktree's root.
- **Not found**: create one alongside the repo, matching the convention used
  by the `linear-ticket` skill:
  `git worktree add ../<repo>-<branch-slug> <branch>`. If the branch only
  exists on the remote, `git fetch origin` first and add the worktree
  tracking `origin/<branch>`.

## 3. Open VS Code

1. If `command -v code` succeeds, run `code <worktree-path>`.
2. Otherwise on macOS fall back to `open -a "Visual Studio Code" <worktree-path>`.
3. If neither works, tell the user the `code` CLI isn't on PATH (installable
   from VS Code via "Shell Command: Install 'code' command in PATH") and give
   them the path so they can open it manually.

## 4. Report

State the branch and the absolute worktree path that was opened, and mention
if a new worktree was created (the user removes it after the PR lands).
