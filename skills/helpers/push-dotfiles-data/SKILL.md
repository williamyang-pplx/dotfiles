---
name: push-dotfiles-data
description: Push new dotfiles changes to the remote's main branch, then pull them and rerun install.sh on this mac and on every devbox that has a workspace in the kitchen right now. Use after making changes in the dotfiles repo, or when asked to push, sync, ship, or roll out dotfiles changes to devboxes (e.g. "/push-dotfiles-data", "push my dotfiles and update the devboxes").
---

# Push dotfiles data

Get dotfiles changes onto `origin/main`, then onto this mac and every devbox
the kitchen has a workspace on. Devboxes replay dotfiles from `main` only on
create/resume, so running ones stay stale until synced by hand.

## 1. Push to main

The dotfiles repo has no PR flow: commits go straight to `main`.

1. Run from the dotfiles checkout the session is working in (often a worktree
   on its own branch). Review `git status` and `git diff`; stage only the
   dotfiles changes this session made, and commit them with a plain
   imperative subject.
2. `git fetch origin`. If `origin/main` is not an ancestor of `HEAD`, rebase
   onto it (`git rebase origin/main`). Stop and ask on any conflict.
3. `git push origin HEAD:main`. Never force-push `main`.

Record the pushed SHA and the range `<old-origin/main>..<new-sha>`.

## 2. Sync this mac

The mac's dotfiles checkout is `~/Documents/dotfiles`; `install.sh` links
everything from wherever it runs, so always run it from that checkout, never
from a session worktree (the links would dangle once the worktree is pruned).

1. `git -C ~/Documents/dotfiles status --porcelain` and `git -C
   ~/Documents/dotfiles branch --show-current` — if the checkout is dirty or
   not on `main`, skip the mac and report it; never stash, reset, or discard.
2. `git -C ~/Documents/dotfiles pull --ff-only origin main`. If it is not a
   fast-forward, skip and report.
3. Run `~/Documents/dotfiles/install.sh`. It is safe to rerun on macOS: its
   apt, AWS CLI, and agent-CLI installs are Linux-only. Report any `Backed up
   existing ...` line, since that means a real file was moved aside.
4. Verify: `git -C ~/Documents/dotfiles log --oneline -1` shows the pushed SHA.

## 3. Find the devboxes

```bash
kitchenctl --json workspace list
```

Take the unique `host` values, skipping `local` (that is this mac). Each host
is also an SSH alias in `~/.ssh/config`. Sync the hosts in parallel.

## 4. Pull on each devbox

The devbox checkout is `~/.dotfiles` (provisioned by `devbox config user
dotfiles`). For each host, over `ssh -o BatchMode=yes -o ConnectTimeout=15
<host>`:

1. `git -C ~/.dotfiles status --porcelain` — if the checkout is dirty or not
   on `main`, skip that host and report it; never stash, reset, or discard
   devbox-local changes.
2. `git -C ~/.dotfiles pull --ff-only origin main`. If it is not a
   fast-forward, skip and report.
3. Apply what changed in the pushed range:
   - **`install.sh` changed** → rerun `~/.dotfiles/install.sh` (it is built
     to replay on every devbox resume, so it is safe to rerun).
   - **Otherwise** → link any new skills the way `install.sh` does, without
     rerunning the whole installer:

     ```bash
     for r in ~/.claude/skills ~/.codex/skills; do
       mkdir -p "$r"
       for s in ~/.dotfiles/skills/*/*/; do
         s="${s%/}"; d="$r/$(basename "$s")"
         [[ -e "$d" && ! -L "$d" ]] && continue   # devbox-local skill; leave it
         ln -sfn "$s" "$d"
       done
     done
     ```

     Edits to already-symlinked files (`.bashrc`, `.tmux.conf`, existing
     skills, `bin/` commands) need nothing beyond the pull.
4. Verify: `git -C ~/.dotfiles log --oneline -1` shows the pushed SHA.

An unreachable host (stopped devbox, SSH timeout) is not an error — report
it; it picks up `main` on its next resume.

## Report

- The pushed SHA and commit subject.
- This mac: synced at `<sha>` with `install.sh` rerun, or skipped and why.
- Per host: synced at `<sha>`, or skipped and why.
- Remind the user that running agent sessions see new skills only after a
  restart.
