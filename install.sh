#!/usr/bin/env bash
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES=(.bashrc .tmux.conf)

for file in "${FILES[@]}"; do
  src="$DOTFILES_DIR/$file"
  dest="$HOME/$file"

  if [[ -L "$dest" ]]; then
    rm "$dest"
  elif [[ -e "$dest" ]]; then
    mv "$dest" "$dest.bak"
    echo "Backed up existing $dest to $dest.bak"
  fi

  ln -s "$src" "$dest"
  echo "Linked $dest -> $src"
done

# .gitconfig is NOT symlinked: devbox bakes auth (a token url.insteadOf rewrite)
# and git identity directly into ~/.gitconfig on provisioning. Symlinking over
# the whole file wipes that out and breaks git push/pull. Apply only specific
# preferences instead, which edits ~/.gitconfig in place and leaves devbox's
# own entries alone.
git config --global core.editor vim
git config --global pull.rebase false
git config --global init.defaultBranch main

VSCODE_SETTINGS_TARGETS=(
  "$HOME/.vscode-server/data/Machine/settings.json"
  "$HOME/.local/share/code-server/User/settings.json"
)

for dest in "${VSCODE_SETTINGS_TARGETS[@]}"; do
  mkdir -p "$(dirname "$dest")"
  if [[ -L "$dest" ]]; then
    rm "$dest"
  elif [[ -e "$dest" ]]; then
    mv "$dest" "$dest.bak"
    echo "Backed up existing $dest to $dest.bak"
  fi

  ln -s "$DOTFILES_DIR/vscode-settings.json" "$dest"
  echo "Linked $dest -> $DOTFILES_DIR/vscode-settings.json"
done

# Keybindings must live in the User (not Machine) profile dir. Note: for
# Remote-SSH (.vscode-server) keybindings are resolved on the *local* client,
# so this file only takes effect in code-server (VSCode Web). For Remote-SSH,
# copy vscode-keybindings.json into your local ~/.config keybindings.json.
VSCODE_KEYBINDING_TARGETS=(
  "$HOME/.vscode-server/data/User/keybindings.json"
  "$HOME/.local/share/code-server/User/keybindings.json"
)

for dest in "${VSCODE_KEYBINDING_TARGETS[@]}"; do
  mkdir -p "$(dirname "$dest")"
  if [[ -L "$dest" ]]; then
    rm "$dest"
  elif [[ -e "$dest" ]]; then
    mv "$dest" "$dest.bak"
    echo "Backed up existing $dest to $dest.bak"
  fi

  ln -s "$DOTFILES_DIR/vscode-keybindings.json" "$dest"
  echo "Linked $dest -> $DOTFILES_DIR/vscode-keybindings.json"
done

VSCODE_EXTENSIONS=(vscodevim.vim)

for cli in code code-server; do
  if command -v "$cli" &>/dev/null; then
    for ext in "${VSCODE_EXTENSIONS[@]}"; do
      "$cli" --install-extension "$ext" --force
      echo "Installed $ext via $cli"
    done
  fi
done

# System packages (devbox images are Debian-based; apt with passwordless sudo).
APT_PACKAGES=(fzf)

missing=()
for pkg in "${APT_PACKAGES[@]}"; do
  dpkg -s "$pkg" &>/dev/null || missing+=("$pkg")
done

if (( ${#missing[@]} )); then
  sudo apt-get update -qq
  sudo apt-get install -y "${missing[@]}"
  echo "Installed apt packages: ${missing[*]}"
fi

# --- MCP servers for the coding agents (Claude Code + Codex) ---
# Remote, OAuth-backed MCP servers. This registers them idempotently; the
# one-time OAuth *login* is interactive (opens a browser) and cannot be
# scripted, so it's a manual follow-up step printed at the end.
#   name|url
MCP_SERVERS=(
  "notion|https://mcp.notion.com/mcp"
  "linear|https://mcp.linear.app/mcp"
  "gmail|https://gmailmcp.googleapis.com/mcp/v1"
  "gcalendar|https://calendarmcp.googleapis.com/mcp/v1"
  "gdrive|https://drivemcp.googleapis.com/mcp/v1"
)

if command -v claude &>/dev/null; then
  for entry in "${MCP_SERVERS[@]}"; do
    name="${entry%%|*}"; url="${entry#*|}"
    if claude mcp get "$name" &>/dev/null; then
      echo "claude: MCP '$name' already registered, skipping"
    elif claude mcp add --scope user --transport http "$name" "$url"; then
      echo "claude: registered MCP '$name'"
    else
      echo "claude: failed to register MCP '$name' (add it manually later)"
    fi
  done
fi

if command -v codex &>/dev/null; then
  for entry in "${MCP_SERVERS[@]}"; do
    name="${entry%%|*}"; url="${entry#*|}"
    if codex mcp get "$name" &>/dev/null; then
      echo "codex: MCP '$name' already registered, skipping"
    elif codex mcp add "$name" --url "$url"; then
      echo "codex: registered MCP '$name'"
    else
      echo "codex: failed to register MCP '$name' (add it manually later)"
    fi
  done
fi

if command -v claude &>/dev/null || command -v codex &>/dev/null; then
  cat <<'EOF'

MCP servers registered. Complete the one-time OAuth login per tool:
  - Claude Code: run `claude`, then `/mcp` and authenticate each server.
  - Codex:       run `codex mcp login <name>` for each server.
Notion and Linear log in with a plain browser OAuth flow. The Google
(gmail/gcalendar/gdrive) servers additionally require your own Google Cloud
OAuth client ID/secret — see README for details.
EOF
fi

echo "Dotfiles installed."
