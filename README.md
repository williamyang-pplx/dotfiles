# dotfiles

Personal shell/tmux/git config, symlinked into place by `install.sh`.

## Manual install

```bash
git clone https://github.com/williamyang-pplx/dotfiles ~/dotfiles
~/dotfiles/install.sh
```

## Devbox auto-install

Register this repo with devbox so it's replayed on every devbox create/resume:

```bash
devbox config user dotfiles set https://github.com/williamyang-pplx/dotfiles --branch main --install install.sh
```

Note: devbox already pre-configures git identity and GitHub auth on its own
(see `docs/dev-guide/01-devbox.md` in the `agi` repo) — the `.gitconfig` here
only adds `[core]`/`[alias]` preferences on top of that, not auth.
