#!/usr/bin/env bash
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES=(.zshrc .tmux.conf)

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

VSCODE_EXTENSIONS=(vscodevim.vim)

for cli in code code-server; do
  if command -v "$cli" &>/dev/null; then
    for ext in "${VSCODE_EXTENSIONS[@]}"; do
      "$cli" --install-extension "$ext" --force
      echo "Installed $ext via $cli"
    done
  fi
done

echo "Dotfiles installed."
