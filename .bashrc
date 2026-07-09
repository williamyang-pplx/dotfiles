# Personal bashrc — devboxes run Linux with bash as the interactive shell.

# Ensure TERM has a valid terminfo entry before loading key bindings.
# Modern terminals (Ghostty, Alacritty, WezTerm, Kitty) set custom TERM values
# that may not exist in the devbox terminfo database. Without a valid entry,
# key bindings can silently fail.
if [[ -n "$TERM" ]] && ! infocmp "$TERM" &>/dev/null; then
    export TERM=xterm-256color
fi

# History
HISTFILE=~/.bash_history
HISTSIZE=10000
HISTFILESIZE=10000
HISTCONTROL=ignoredups:erasedups   # ignore duplicate commands
shopt -s histappend                # append rather than overwrite on exit
# Share history across concurrent sessions (append, reload) on each prompt.
PROMPT_COMMAND="history -a; history -n; ${PROMPT_COMMAND:-}"

# Sensible shell options
shopt -s checkwinsize              # keep $LINES/$COLUMNS accurate after resize
shopt -s cmdhist                   # store multi-line commands as one entry

# direnv (was an Oh My Zsh plugin; hook it directly under bash)
if command -v direnv &>/dev/null; then
  eval "$(direnv hook bash)"
fi

# Git-aware prompt (bira-ish: user@host, cwd, branch)
if [[ -f /usr/lib/git-core/git-sh-prompt ]]; then
  source /usr/lib/git-core/git-sh-prompt
elif [[ -f /etc/bash_completion.d/git-prompt ]]; then
  source /etc/bash_completion.d/git-prompt
fi
export GIT_PS1_SHOWDIRTYSTATE=1
if type __git_ps1 &>/dev/null; then
  PS1='\[\e[32m\]\u@\h\[\e[0m\]:\[\e[34m\]\w\[\e[33m\]$(__git_ps1 " (%s)")\[\e[0m\]\$ '
else
  PS1='\[\e[32m\]\u@\h\[\e[0m\]:\[\e[34m\]\w\[\e[0m\]\$ '
fi

# Aliases
alias ll='ls -alF'
alias la='ls -A'
alias gs='git status'
alias gd='git diff'
alias gco='git checkout'

# "cook" aliases: run the coding agents fully autonomously (no approval
# prompts, no sandbox). Safe here because devboxes are isolated, disposable
# runners — do NOT copy these onto a trusted workstation.
alias claude-cook='claude --dangerously-skip-permissions'
alias codex-cook='codex --dangerously-bypass-approvals-and-sandbox'

# fzf: Ctrl-R history search, Ctrl-T file finder, Alt-C cd, tab completion
if command -v fzf &>/dev/null; then
  if fzf --bash &>/dev/null; then
    source <(fzf --bash)
  else
    for f in /usr/share/doc/fzf/examples/key-bindings.bash \
             /usr/share/doc/fzf/examples/completion.bash; do
      [[ -f "$f" ]] && source "$f"
    done
  fi
fi

# Coding-agent MCP plugin (deferred install).
# install.sh can't do this: devbox replays dotfiles during provisioning,
# *before* claude/codex are installed, so `command -v claude` fails there and
# the setup is silently skipped. Do it here instead, on interactive shell
# startup, once the CLIs exist. mcp-setup.sh is content-hash idempotent, so this
# is cheap after the plugin is installed and automatically re-runs when the
# checked-in plugin files change.
if [[ $- == *i* ]] && { command -v claude || command -v codex; } &>/dev/null; then
  _dotfiles_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null)")"
  [[ -x "$_dotfiles_dir/mcp-setup.sh" ]] && "$_dotfiles_dir/mcp-setup.sh" --no-login
  unset _dotfiles_dir
fi

# Drop the zsh->bash handoff guard once we've actually landed in bash. It has
# to be exported (so it survives the exec from zsh), but that means tmux's
# server bakes it into its global environment table the first time a session
# starts under it, and hands that stale value to every later pane/window.
# Those fresh zsh shells then see the guard already set and never hand off,
# leaving the pane stuck in zsh (where this bash-only file errors if sourced
# manually). Unsetting here keeps it out of the environment tmux captures.
unset DOTFILES_ZSH_HANDOFF

# Personal customizations below
