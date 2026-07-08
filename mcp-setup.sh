#!/usr/bin/env bash
# Register remote MCP servers for the coding agents (Claude Code + Codex).
#
# Why this is separate from install.sh: devbox replays dotfiles during
# provisioning, *before* `claude`/`codex` are installed. Registering there is a
# silent no-op — `command -v claude` fails, the block is skipped, and the box
# still comes up `running`, so nothing signals the miss. This script is invoked
# from ~/.bashrc on interactive shell startup instead, so it runs once the agent
# CLIs are actually present. It is idempotent (skips already-registered servers)
# and writes a sentinel after a clean pass so the shell only runs it once.
#
# To re-register after installing a new agent CLI (e.g. codex arrives later),
# run this script directly or `rm ~/.cache/dotfiles/mcp-registered`.
set -uo pipefail   # deliberately NOT -e: one failed `add` must not skip the rest

#   name|url
MCP_SERVERS=(
  "notion|https://mcp.notion.com/mcp"
  "linear|https://mcp.linear.app/mcp"
  "gmail|https://gmailmcp.googleapis.com/mcp/v1"
  "gcalendar|https://calendarmcp.googleapis.com/mcp/v1"
  "gdrive|https://drivemcp.googleapis.com/mcp/v1"
)

STATE_DIR="$HOME/.cache/dotfiles"
SENTINEL="$STATE_DIR/mcp-registered"
LOCK="$STATE_DIR/mcp-setup.lock"
mkdir -p "$STATE_DIR"

# Single-flight: if another shell is already registering (racing tmux panes),
# bail quietly. mkdir is atomic, so exactly one runner wins.
if ! mkdir "$LOCK" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

failures=0
registered=0

if command -v claude &>/dev/null; then
  for entry in "${MCP_SERVERS[@]}"; do
    name="${entry%%|*}"; url="${entry#*|}"
    if claude mcp get "$name" &>/dev/null; then
      continue
    elif claude mcp add --scope user --transport http "$name" "$url" &>/dev/null; then
      echo "claude: registered MCP '$name'"
      registered=$((registered + 1))
    else
      echo "claude: failed to register MCP '$name' (add it manually later)" >&2
      failures=$((failures + 1))
    fi
  done
fi

if command -v codex &>/dev/null; then
  for entry in "${MCP_SERVERS[@]}"; do
    name="${entry%%|*}"; url="${entry#*|}"
    if codex mcp get "$name" &>/dev/null; then
      continue
    elif codex mcp add "$name" --url "$url" &>/dev/null; then
      echo "codex: registered MCP '$name'"
      registered=$((registered + 1))
    else
      echo "codex: failed to register MCP '$name' (add it manually later)" >&2
      failures=$((failures + 1))
    fi
  done
fi

# Only mark done on a clean pass, so transient failures are retried next shell.
if (( failures == 0 )); then
  : > "$SENTINEL"
fi

if (( registered > 0 )); then
  cat <<'EOF'
MCP servers registered. Complete the one-time OAuth login per tool:
  - Claude Code: run `claude`, then `/mcp` and authenticate each server.
  - Codex:       run `codex mcp login <name>` for each server.
Notion and Linear log in with a plain browser OAuth flow. The Google
(gmail/gcalendar/gdrive) servers additionally require your own Google Cloud
OAuth client ID/secret — see README for details.
EOF
fi
