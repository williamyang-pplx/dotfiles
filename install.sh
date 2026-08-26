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

# Agent skills (Claude Code + Codex). Skills live under skills/<category>/<skill>/
# with a SKILL.md; the categories (pr-review, pr-setup, style, helpers) are
# for organizing the repo only. Both CLIs discover skills by scanning flat dirs on
# disk (Claude Code: ~/.claude/skills, Codex: ~/.codex/skills), so each skill
# dir is linked individually into the flat root — unlike MCP registration this
# is safe to do at provisioning time before the CLIs exist.
# Skills are linked one-by-one (not the whole dir) so skills created directly
# on a devbox can coexist without landing in the repo.
SKILL_DEST_ROOTS=("$HOME/.claude/skills" "$HOME/.codex/skills")

for dest_root in "${SKILL_DEST_ROOTS[@]}"; do
  mkdir -p "$dest_root"
  for src in "$DOTFILES_DIR"/skills/*/*/; do
    src="${src%/}"
    [[ -d "$src" ]] || continue
    dest="$dest_root/$(basename "$src")"

    if [[ -L "$dest" ]]; then
      rm "$dest"
    elif [[ -e "$dest" ]]; then
      mv "$dest" "$dest.bak"
      echo "Backed up existing $dest to $dest.bak"
    fi

    ln -s "$src" "$dest"
    echo "Linked $dest -> $src"
  done
done

# Personal commands, symlinked onto PATH.
BIN_FILES=(kitchen)
mkdir -p "$HOME/.local/bin"

for file in "${BIN_FILES[@]}"; do
  src="$DOTFILES_DIR/bin/$file"
  dest="$HOME/.local/bin/$file"

  if [[ -L "$dest" ]]; then
    rm "$dest"
  elif [[ -e "$dest" ]]; then
    mv "$dest" "$dest.bak"
    echo "Backed up existing $dest to $dest.bak"
  fi

  ln -s "$src" "$dest"
  echo "Linked $dest -> $src"
done

# Claude Code statusline (branch, model, context %, cost). Vendored from agi's
# pplx-common plugin so air-only devboxes (no agi checkout) still get it. Safe
# to run before claude is installed since it only writes ~/.claude/settings.json;
# non-destructive of a statusline the user already customized (see script).
if command -v python3 &>/dev/null; then
  python3 "$DOTFILES_DIR/scripts/setup_statusline.py"
  echo "Configured Claude Code statusline"
fi

# System packages (devbox images are Debian-based; apt with passwordless sudo).
# Guarded on dpkg so the script also runs on macOS, which has no apt.
APT_PACKAGES=(fzf unzip)

if command -v dpkg &>/dev/null; then
  missing=()
  for pkg in "${APT_PACKAGES[@]}"; do
    dpkg -s "$pkg" &>/dev/null || missing+=("$pkg")
  done

  if (( ${#missing[@]} )); then
    sudo apt-get update -qq
    sudo apt-get install -y "${missing[@]}"
    echo "Installed apt packages: ${missing[*]}"
  fi
fi

# AWS CLI v2. Not available from Debian apt (apt only ships the long-stale v1
# `awscli`), so use Amazon's official bundled installer, which drops a
# self-contained runtime in /usr/local/aws-cli and symlinks it onto PATH.
# Linux-only: the installer has no macOS build (use `brew install awscli`
# there). Non-fatal — a network failure during provisioning shouldn't abort the
# rest of the script and mark the devbox degraded.
if [[ "$(uname -s)" == "Linux" ]] && ! command -v aws &>/dev/null; then
  case "$(uname -m)" in
    x86_64) aws_arch=x86_64 ;;
    aarch64 | arm64) aws_arch=aarch64 ;;
    *) aws_arch="" ;;
  esac

  if [[ -z "$aws_arch" ]]; then
    echo "warn: unsupported arch $(uname -m) for AWS CLI (skipping)" >&2
  elif ! command -v unzip &>/dev/null; then
    echo "warn: unzip missing, cannot install AWS CLI (skipping)" >&2
  else
    aws_tmp="$(mktemp -d)"
    if curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$aws_arch.zip" \
         -o "$aws_tmp/awscliv2.zip" \
       && unzip -q "$aws_tmp/awscliv2.zip" -d "$aws_tmp" \
       && sudo "$aws_tmp/aws/install" --update; then
      echo "Installed AWS CLI: $(aws --version 2>&1)"
    else
      echo "warn: failed to install AWS CLI (skipping)" >&2
    fi
    rm -rf "$aws_tmp"
  fi
fi

# MCP server registration is intentionally NOT done here. devbox replays
# dotfiles during provisioning, *before* claude/codex are installed, so any
# `claude mcp add` at this point is a silent no-op (command -v fails). It's
# handled instead by mcp-setup.sh, invoked from ~/.bashrc on interactive shell
# startup once the agent CLIs actually exist. See mcp-setup.sh for details.

echo "Dotfiles installed."
