---
name: create-devbox
description: Create a new large devbox with the `devbox` CLI, grow its Home Storage to 500 GiB, and open a kitchen workspace on it. Use when asked to create, spin up, or make a new devbox (e.g. "/create-devbox", "make me a new devbox called foo").
---

# Create devbox

Create a `large` tier devbox, then grow its Home Storage to 500 GiB. The
`large` tier ships with 400 GiB of Home Storage and `devbox create` has no disk
flag, so the growth is a second step through `devbox change`. Home Storage
only grows, never shrinks, and the growth needs no restart.

## 1. Pick the name

Use the name the user gave. Without one, take the next free `willbox-<n>` from
`devbox list`. If the name is already taken, stop and ask.

## 2. Create

```bash
devbox create <name> --tier large -y
```

Keep the CLI defaults for everything else (agi repo, amd64, Docker-in-Docker)
unless the user asks otherwise: `--repo`/`--branch` for another repo,
`--accelerator h200` for a GPU, `--kvm`, `--ssd`. Check `devbox create --help`
before passing a flag not listed here.

## 3. Grow Home Storage to 500 GiB

```bash
devbox change <name> --home-storage 500Gi -y
```

This waits until the volume is resized. If it fails because the box is still
provisioning, wait for `devbox info <name>` to show it running and retry.

## 4. Verify

`devbox change <name>` (no flags) prints the storage state; Home Storage
`Observed` and `PVC capacity` must both read 500 GiB.

## 5. Create a kitchen workspace

`devbox create` already added an SSH alias named `<name>` to `~/.ssh/config`,
and it cloned the repo to `~/<repo name>` on the box (`~/agi` by default).
Open a kitchen workspace on that checkout, named after the devbox:

```bash
kitchenctl workspace new --host <name> --repo ~/agi --name <name>
```

Use the matching `~/<repo name>` if the box was created with `--repo`. Then
confirm `kitchenctl --json workspace list` shows a workspace with
`host: <name>`.

## Report

- The devbox name and status.
- Home Storage and Docker Storage sizes.
- The kitchen workspace name and repo path.
- How to connect: `devbox ssh <name>`.
