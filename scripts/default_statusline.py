#!/usr/bin/env python3
# Vendored from agi's .agents/plugins/pplx-common/scripts/default_statusline.py
# so devboxes without an agi checkout (e.g. air-only boxes) still get the
# branch/model/context/cost statusline. Keep in sync with the agi original.
import json
import subprocess
import sys

# Perplexity receives a 30% discount on Anthropic token list pricing. Claude Code
# reports session cost at list price (total_cost_usd), so scale it down to reflect
# actual spend before displaying.
ANTHROPIC_TOKEN_DISCOUNT = 0.30


def get_git_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        # Check if in detached HEAD state
        result = subprocess.run(
            ["git", "--no-optional-locks", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return "(detached)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "(no git)"


def get_changed_files_count() -> int:
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            lines = [line for line in result.stdout.strip().split("\n") if line]
            return len(lines)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return 0


def truncate_branch(branch: str, max_length: int = 40) -> str:
    if len(branch) <= max_length:
        return branch
    return branch[: max_length - 1] + "…"


def format_changed_files(count: int) -> str:
    if count == 0:
        return "(no local changes)"
    elif count == 1:
        return "(+1 local file changed)"
    else:
        return f"(+{count} local files changed)"


def main() -> None:
    data = json.load(sys.stdin)

    context_percent = data.get("context_window", {}).get("used_percentage", 0)
    list_cost = data.get("cost", {}).get("total_cost_usd", 0)
    cost = list_cost * (1 - ANTHROPIC_TOKEN_DISCOUNT)
    model_name = data.get("model", {}).get("display_name", "Unknown")
    git_branch = get_git_branch()
    changed_files_count = get_changed_files_count()

    branch_display = truncate_branch(git_branch)
    changes_display = format_changed_files(changed_files_count)
    model_display = f"Model: {model_name}"
    context_display = f"Context: {context_percent:.1f}%"
    cost_display = f"${cost:.2f}"

    branch_section = f"{branch_display} {changes_display}"
    print(
        f"{branch_section:^65} | {model_display:^15} | {context_display:^15} | {cost_display:^8}"
    )


if __name__ == "__main__":
    main()
