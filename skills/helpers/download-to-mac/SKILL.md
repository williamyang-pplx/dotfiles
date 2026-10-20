---
name: download-to-mac
description: Copy files from the devbox this session runs on down to William's MacBook, through the kitchen's `download` plugin. Use when asked to download, send, copy, or pull a file or folder to the mac / laptop / local machine (e.g. "download this plot to my mac", "send me report.html", "copy the logs to my laptop").
---

# Download files to the mac

The kitchen app on the mac keeps a relay open to every devbox it has a
workspace on (`~/.kitchen/kitchen.sock`). Its `download` plugin runs on the
mac: it rsyncs the devbox's `~/outbox/` into
`~/Downloads/devbox/<host>/` on the mac and deletes each file from the outbox
once it has arrived.

## 1. Check where this session runs

```bash
kitchenctl --json identify
```

- `caller.workspace.host` is `local`: this session is already on the mac.
  Give the path; there is nothing to download.
- The command fails (exit 3, or no `kitchenctl`): this session is not in a
  kitchen tab. Tell William, and give the command to run on the mac:
  `scp <host>:<absolute path> ~/Downloads/`.

Otherwise `host` is the devbox name; it names the folder the files land in.

## 2. Stage the files

Copy (do not move) each file or folder into the outbox:

```bash
mkdir -p ~/outbox && cp -r <paths> ~/outbox/
```

Subfolders keep their layout. A file with the same name already in
`~/Downloads/devbox/<host>/` on the mac is overwritten, so rename the copy
first if that would lose something.

## 3. Pull

```bash
kitchenctl plugin run download.pull
```

This only starts the pull. Wait for the outbox to empty: rsync deletes each
file only after it arrived on the mac.

```bash
timeout 300 bash -c 'until [ -z "$(find ~/outbox -type f -print -quit)" ]; do sleep 2; done'
```

For large files, use a longer timeout.

## 4. Report

- **Outbox empty:** give the mac paths, `~/Downloads/devbox/<host>/<name>`.
  The mac shows a notification and opens the file in Finder.
- **Files still in the outbox:** the pull failed or is still running.
  William sees the error in a toast on the mac (and in `kitchenctl plugin
  logs download` there). Leave the files in the outbox; the next pull picks
  them up.
