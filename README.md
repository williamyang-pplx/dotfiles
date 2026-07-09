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

MCP servers are defined once in the `dotfiles-mcp` plugin:

```text
.agents/plugins/dotfiles-mcp/.mcp.json
```

The checked-in plugin manifests make the same server list available to both Claude Code
and Codex:

```text
.claude-plugin/marketplace.json
.agents/plugins/marketplace.json
.agents/plugins/dotfiles-mcp/.claude-plugin/plugin.json
.agents/plugins/dotfiles-mcp/.codex-plugin/plugin.json
```

`mcp-setup.sh` installs or updates that plugin in `claude` and `codex`, whichever is
present. It does not maintain separate client-specific MCP server definitions.

**Why not in `install.sh`?** devbox replays dotfiles during provisioning, *before*
`claude`/`codex` are installed, so an agent setup command there is a silent no-op (and
the box still comes up `running`, hiding the miss). Instead, `.bashrc` runs
`mcp-setup.sh --no-login` on interactive shell startup once the CLIs exist. The script is
content-hash idempotent: it writes `~/.cache/dotfiles/mcp-plugin-stamp` after a clean
pass and automatically reruns when the checked-in plugin files change.

To force a reinstall/update:

```bash
~/dotfiles/mcp-setup.sh --force
```

OAuth login is interactive and intentionally separate from shell startup:

```bash
~/dotfiles/mcp-setup.sh --login
```

That runs `claude mcp login <name>` and `codex mcp login <name>` for each configured
server: Notion, Linear, Gmail, Google Calendar, and Google Drive. Restart Claude Code or
Codex after installing/updating the plugin if either agent was already running.

Notion and Linear use a plain browser OAuth flow that works out of the box. The Google
Workspace servers may require a Google Cloud OAuth client with the Gmail, Calendar, and
Drive APIs enabled — see
[Google's MCP setup docs](https://developers.google.com/workspace/guides/configure-mcp-servers).
Add or remove servers by editing `.agents/plugins/dotfiles-mcp/.mcp.json`; bump
`.agents/plugins/dotfiles-mcp/plugin.yaml` if agent plugin caches need to see a new
version.

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
