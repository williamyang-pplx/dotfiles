#!/usr/bin/env bash
# Install the dotfiles MCP plugin for Claude Code and Codex.
#
# The MCP server list is authored once in:
#
#   .agents/plugins/dotfiles-mcp/.mcp.json
#
# Claude Code and Codex then consume that same list through generated plugin
# manifests and marketplaces checked into this repo. This keeps the setup in
# step with AGI's cross-agent plugin layout while avoiding duplicated
# client-specific MCP definitions.
set -uo pipefail   # deliberately not -e: one failed client must not skip the other

PLUGIN_NAME="dotfiles-mcp"
MARKETPLACE_NAME="dotfiles"
MCP_SERVER_NAMES=(notion linear gmail gcalendar gdrive)

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$HOME/.cache/dotfiles"
SETUP_STAMP_FILE="$STATE_DIR/mcp-plugin-stamp"
AUTH_STAMP_FILE="$STATE_DIR/mcp-auth-stamp"
LEGACY_SENTINEL="$STATE_DIR/mcp-registered"
LOCK="$STATE_DIR/mcp-setup.lock"

mkdir -p "$STATE_DIR"

usage() {
  cat <<EOF
Usage: $0 [--login] [--no-login] [--force]

Installs or updates the $PLUGIN_NAME plugin for Claude Code and Codex.

Options:
  --login     Also run interactive OAuth login for every MCP server in both clients.
  --no-login  Only install/update the plugin. This is the default for shell startup.
  --force     Run even when the checked-in plugin files match the previous run.
EOF
}

force=0
login=0

for arg in "$@"; do
  case "$arg" in
    --force)
      force=1
      ;;
    --login)
      login=1
      ;;
    --no-login)
      login=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! mkdir "$LOCK" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

plugin_stamp() {
  (
    cd "$DOTFILES_DIR" || exit 1
    find \
      .plugins-catalog.yaml \
      .agents/plugins/marketplace.json \
      .agents/plugins/"$PLUGIN_NAME" \
      .claude-plugin/marketplace.json \
      -type f -print0 \
      | sort -z \
      | xargs -0 sha256sum \
      | sha256sum \
      | awk '{print $1}'
  )
}

current_stamp="$(plugin_stamp 2>/dev/null || true)"
if [[ -z "$current_stamp" ]]; then
  echo "mcp-setup: failed to compute plugin stamp from $DOTFILES_DIR" >&2
  exit 1
fi

previous_stamp=""
if [[ -f "$SETUP_STAMP_FILE" ]]; then
  previous_stamp="$(<"$SETUP_STAMP_FILE")"
fi

if (( force == 0 && login == 0 )) && [[ "$previous_stamp" == "$current_stamp" ]]; then
  exit 0
fi

failures=0
actions=0

log_action() {
  echo "mcp-setup: $*"
  actions=$((actions + 1))
}

warn_failure() {
  echo "mcp-setup: $*" >&2
  failures=$((failures + 1))
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

codex_marketplace_configured() {
  codex plugin marketplace list --json 2>/dev/null \
    | grep -q '"name"[[:space:]]*:[[:space:]]*"'"$MARKETPLACE_NAME"'"'
}

codex_plugin_installed() {
  codex plugin list --json 2>/dev/null \
    | grep -q '"name"[[:space:]]*:[[:space:]]*"'"$PLUGIN_NAME"'"'
}

install_claude_plugin() {
  if ! command_exists claude; then
    return
  fi

  if claude plugin marketplace add --scope user "$DOTFILES_DIR" >/dev/null 2>&1; then
    log_action "added Claude Code marketplace '$MARKETPLACE_NAME'"
  elif claude plugin marketplace update "$MARKETPLACE_NAME" >/dev/null 2>&1; then
    log_action "refreshed Claude Code marketplace '$MARKETPLACE_NAME'"
  else
    warn_failure "failed to add or refresh Claude Code marketplace '$MARKETPLACE_NAME'"
    return
  fi

  if claude plugin update --scope user "$PLUGIN_NAME" >/dev/null 2>&1; then
    log_action "updated Claude Code plugin '$PLUGIN_NAME'"
  elif claude plugin install --scope user "$PLUGIN_NAME@$MARKETPLACE_NAME" >/dev/null 2>&1; then
    log_action "installed Claude Code plugin '$PLUGIN_NAME'"
  else
    warn_failure "failed to install or update Claude Code plugin '$PLUGIN_NAME'"
  fi
}

install_codex_plugin() {
  if ! command_exists codex; then
    return
  fi

  if codex_marketplace_configured; then
    :
  elif codex plugin marketplace add "$DOTFILES_DIR" --json >/dev/null 2>&1; then
    log_action "added Codex marketplace '$MARKETPLACE_NAME'"
  else
    warn_failure "failed to add Codex marketplace '$MARKETPLACE_NAME'"
    return
  fi

  if codex_plugin_installed; then
    if [[ "$previous_stamp" == "$current_stamp" && "$force" == 0 ]]; then
      return
    fi

    if codex plugin remove "$PLUGIN_NAME@$MARKETPLACE_NAME" --json >/dev/null 2>&1; then
      log_action "removed stale Codex plugin '$PLUGIN_NAME'"
    else
      warn_failure "failed to remove stale Codex plugin '$PLUGIN_NAME'"
      return
    fi
  fi

  if codex plugin add "$PLUGIN_NAME@$MARKETPLACE_NAME" --json >/dev/null 2>&1; then
    log_action "installed Codex plugin '$PLUGIN_NAME'"
  elif codex_plugin_installed; then
    log_action "Codex plugin '$PLUGIN_NAME' is already installed"
  else
    warn_failure "failed to install Codex plugin '$PLUGIN_NAME'"
  fi
}

run_logins_for_client() {
  local client="$1"

  if ! command_exists "$client"; then
    return
  fi

  for server_name in "${MCP_SERVER_NAMES[@]}"; do
    if "$client" mcp login "$server_name"; then
      log_action "authenticated $client MCP '$server_name'"
    else
      warn_failure "failed to authenticate $client MCP '$server_name'"
    fi
  done
}

install_claude_plugin
install_codex_plugin

if (( failures == 0 )); then
  printf '%s\n' "$current_stamp" > "$SETUP_STAMP_FILE"
  rm -f "$LEGACY_SENTINEL"
fi

if (( login == 1 )); then
  if [[ ! -t 0 ]]; then
    warn_failure "--login requires an interactive terminal"
  else
    run_logins_for_client claude
    run_logins_for_client codex
    if (( failures == 0 )); then
      printf '%s\n' "$current_stamp" > "$AUTH_STAMP_FILE"
    fi
  fi
elif (( actions > 0 )); then
  cat <<EOF
mcp-setup: MCP plugin installed for available coding agents.
mcp-setup: restart Claude Code/Codex if they were already running.
mcp-setup: authenticate the servers with:
  $DOTFILES_DIR/mcp-setup.sh --login
EOF
fi

exit 0
