# dotfiles

Personal shell/tmux config for Perplexity Linux devboxes, symlinked into place by
`install.sh`. The interactive shell is bash (`.bashrc`); the devbox default login
shell is zsh, so `.zshrc` hands interactive sessions off to bash (see below). Git
preferences are applied via targeted `git config --global` calls instead (see below).
Also installs the
[VSCodeVim](https://marketplace.visualstudio.com/items?itemName=vscodevim.vim) extension
for `code` (Remote-SSH) and `code-server` (VSCode Web), whichever is present, and the
[`fzf`](https://github.com/junegunn/fzf) fuzzy finder via `apt` (with bash key bindings and
completion wired into `.bashrc`).

## Shell: zsh → bash handoff

Devboxes default to **zsh** as the login shell, but this config targets bash. `.zshrc`
is symlinked in and, for interactive sessions, immediately `exec bash` so `.bashrc`
loads. This is safe because devbox sets up the login environment (PATH, direnv, AWS,
greeter) in the *system* zsh files (`/etc/zsh/zprofile` → `/etc/profile`) which run
before `~/.zshrc`, so bash inherits a fully-configured environment. Non-interactive zsh
(scripts, `devbox exec`, managed agent tooling) is left alone.

## Shell aliases

`.bashrc` defines `claude-cook` and `codex-cook`, which run the agents with all
approval prompts and sandboxing disabled (`claude --dangerously-skip-permissions` /
`codex --dangerously-bypass-approvals-and-sandbox`). These are only safe because
devboxes are isolated, disposable runners — do not use them on a trusted machine.

## VSCode

`vscode-settings.json` puts the panel on the right by default. `vscode-keybindings.json`
binds `cmd+1`..`cmd+8` to the 1st–8th tab in the active editor group and `cmd+9` to the
last (rightmost) tab. Both are symlinked into the code-server and `.vscode-server` User
dirs. Note: for **Remote-SSH**, VSCode resolves keybindings on the *local* client, so the
keybinding file only takes effect in **code-server** (VSCode Web); for Remote-SSH, copy
`vscode-keybindings.json` into your local `keybindings.json`.

## MCP servers (Claude Code + Codex)

`mcp-setup.sh` registers remote MCP servers for Notion, Linear, and Google Workspace
(Gmail/Calendar/Drive) in `claude` and `codex`, whichever is present.

**Why not in `install.sh`?** devbox replays dotfiles during provisioning, *before*
`claude`/`codex` are installed, so a `claude mcp add` there is a silent no-op (and the
box still comes up `running`, hiding the miss). Instead, `.bashrc` runs `mcp-setup.sh`
on interactive shell startup once the CLIs exist. It's idempotent and one-shot: it
writes `~/.cache/dotfiles/mcp-registered` after a clean pass and is skipped thereafter.
To re-register after installing a new agent CLI, run `~/.dotfiles/mcp-setup.sh` or
`rm ~/.cache/dotfiles/mcp-registered`.

Registration is idempotent; the one-time OAuth login is interactive and must be done
manually afterward:

- **Claude Code**: `claude` → `/mcp` → authenticate each server.
- **Codex**: `codex mcp login <name>` for each server.

Notion and Linear use a plain browser OAuth flow that works out of the box. The Google
Workspace servers additionally require **your own** Google Cloud OAuth client ID/secret
(create a Web-application OAuth client, enable the Gmail/Calendar/Drive APIs) — see
[Google's MCP setup docs](https://developers.google.com/workspace/guides/configure-mcp-servers).
Add or remove servers by editing the `MCP_SERVERS` list in `mcp-setup.sh`.

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
