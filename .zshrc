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
# Linux only: on macOS (personal machine) zsh is the shell we actually want,
# with its own plugins below — handing off there would strand every terminal
# in an unconfigured bash.
if [[ "$OSTYPE" == linux* && -o interactive && -z "${DOTFILES_ZSH_HANDOFF:-}" ]] && command -v bash >/dev/null 2>&1; then
  export DOTFILES_ZSH_HANDOFF=1   # guard against re-entry if bash ever re-execs zsh
  exec bash
fi

# Reached only when the handoff is skipped (macOS, bash missing, or non-interactive).
# Fall back to the base image's Oh My Zsh config if it was preserved.
[[ -r ~/.zshrc.bak ]] && source ~/.zshrc.bak

# Fish-style autosuggestions from history (Homebrew, macOS)
[[ -r /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]] &&
  source /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh

# Tab accepts the visible autosuggestion (POSTDISPLAY holds its text);
# otherwise fall through to fzf's completion widget, or plain completion
# when fzf isn't loaded. Only bound when the plugin actually loaded, so a
# missing Homebrew package leaves Tab untouched.
if (( ${+functions[_zsh_autosuggest_accept]} )); then
  _tab_accept_suggestion_or_complete() {
    if [[ -n "$POSTDISPLAY" ]]; then
      zle autosuggest-accept
    elif zle -l fzf-completion; then
      zle fzf-completion
    else
      zle expand-or-complete
    fi
  }
  zle -N _tab_accept_suggestion_or_complete
  bindkey '^I' _tab_accept_suggestion_or_complete
fi

# git-spice (Homebrew ships the binary as `git-spice` to avoid clashing with Ghostscript's `gs`)
alias gs='git-spice'
