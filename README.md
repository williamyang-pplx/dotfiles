# dotfiles

Personal shell/tmux config, symlinked into place by `install.sh`. Git preferences are
applied via targeted `git config --global` calls instead (see below). Also installs the
[VSCodeVim](https://marketplace.visualstudio.com/items?itemName=vscodevim.vim) extension
for `code` (Remote-SSH) and `code-server` (VSCode Web), whichever is present, and the
[`fzf`](https://github.com/junegunn/fzf) fuzzy finder via `apt` (with zsh key bindings and
completion wired into `.zshrc`).

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

Note: devbox pre-configures git identity and GitHub auth by writing directly into
`~/.gitconfig` (see `docs/dev-guide/01-devbox.md` in the `agi` repo), including a
token-based `url.insteadOf` rewrite. `install.sh` deliberately does **not** symlink
`.gitconfig` — doing so would wipe that out and break `git push`/`pull`. Instead it
runs `git config --global core.editor|pull.rebase|init.defaultBranch`, which edits
`~/.gitconfig` in place and leaves devbox's own entries alone.
