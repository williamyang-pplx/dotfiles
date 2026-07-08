# Personal zshrc — the devbox default login shell is zsh, but this dotfiles set
# targets bash (prompt, aliases, direnv/fzf hooks, and the coding-agent MCP
# bootstrap all live in ~/.bashrc). Hand interactive zsh sessions off to bash so
# that configuration actually loads.
#
# This is safe with respect to the login environment: devbox establishes PATH,
# direnv, AWS creds, and the greeter in the *system* zsh files
# (/etc/zsh/zprofile → /etc/profile) which run before ~/.zshrc, so the exec'd
# bash inherits a fully set-up environment. Non-interactive zsh (scripts,
# `devbox exec`, managed agent tooling) is left untouched so nothing that
# expects a plain shell breaks.
if [[ -o interactive && -z "${DOTFILES_ZSH_HANDOFF:-}" ]] && command -v bash >/dev/null 2>&1; then
  export DOTFILES_ZSH_HANDOFF=1   # guard against re-entry if bash ever re-execs zsh
  exec bash
fi

# Reached only when the handoff is skipped (bash missing, or non-interactive).
# Fall back to the base image's Oh My Zsh config if it was preserved.
[[ -r ~/.zshrc.bak ]] && source ~/.zshrc.bak
