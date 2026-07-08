#!/usr/bin/env bash
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# .zshrc is symlinked too: the devbox default login shell is zsh, and our
# .zshrc hands interactive sessions off to bash (where the real config lives).
FILES=(.bashrc .zshrc .tmux.conf)

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
      # Non-fatal: code-server's extension gallery may not be reachable during
      # provisioning. Don't let a failed install abort the script (which would
      # mark the devbox degraded and skip everything after this).
      if "$cli" --install-extension "$ext" --force; then
        echo "Installed $ext via $cli"
      else
        echo "warn: failed to install $ext via $cli (skipping)" >&2
      fi
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

# MCP server registration is intentionally NOT done here. devbox replays
# dotfiles during provisioning, *before* claude/codex are installed, so any
# `claude mcp add` at this point is a silent no-op (command -v fails). It's
# handled instead by mcp-setup.sh, invoked from ~/.bashrc on interactive shell
# startup once the agent CLIs actually exist. See mcp-setup.sh for details.

echo "Dotfiles installed."
