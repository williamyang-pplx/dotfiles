# Personal zshrc — layered on top of the devbox default (Oh My Zsh).

# Ensure TERM has a valid terminfo entry before Oh My Zsh loads key bindings.
# Modern terminals (Ghostty, Alacritty, WezTerm, Kitty) set custom TERM values
# that may not exist in the devbox terminfo database. Without a valid entry,
# zsh's $terminfo[] array is empty and key bindings silently fail.
if [[ -n "$TERM" ]] && ! infocmp "$TERM" &>/dev/null; then
    export TERM=xterm-256color
fi

export ZSH="/opt/oh-my-zsh"
export ZSH_CUSTOM="$HOME/.oh-my-zsh-custom"
ZSH_THEME="bira"
plugins=(git direnv)
source "$ZSH/oh-my-zsh.sh"

HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=10000
setopt appendhistory
setopt sharehistory
setopt hist_ignore_dups

# Aliases
alias ll='ls -alF'
alias la='ls -A'
alias gs='git status'
alias gd='git diff'
alias gco='git checkout'

# fzf: Ctrl-R history search, Ctrl-T file finder, Alt-C cd, tab completion
if command -v fzf &>/dev/null; then
  if fzf --zsh &>/dev/null; then
    source <(fzf --zsh)
  else
    for f in /usr/share/doc/fzf/examples/key-bindings.zsh \
             /usr/share/doc/fzf/examples/completion.zsh; do
      [[ -f "$f" ]] && source "$f"
    done
  fi
fi

# Personal customizations below
