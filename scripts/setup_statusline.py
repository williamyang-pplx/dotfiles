#!/usr/bin/env python3
# Vendored from agi's .agents/plugins/pplx-common/scripts/setup_statusline.py;
# keep in sync with the agi original.
"""Configure user's statusline setting if not already set.

Only installs the default statusline when the user has not provisioned a
custom one.  A statusline is considered "custom" when the existing config
contains a ``command`` key whose value does *not* reference
``default_statusline.py``.
"""

import json
from pathlib import Path
from typing import Any

DEFAULT_STATUSLINE_MARKER = "default_statusline.py"


def _has_custom_statusline(settings: dict[str, Any]) -> bool:
    """Return True if the user has configured a non-default statusline."""
    statusline = settings.get("statusLine")
    if not isinstance(statusline, dict):
        return False
    command = statusline.get("command")
    if not isinstance(command, str):
        return False
    return DEFAULT_STATUSLINE_MARKER not in command


def main() -> None:
    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    script_path = (Path(__file__).parent / "default_statusline.py").resolve()
    statusline_config: dict[str, Any] = {
        "type": "command",
        "command": f"python3 {script_path}",
        "padding": 0,
    }

    if not settings_path.exists():
        settings_path.write_text(
            json.dumps({"statusLine": statusline_config}, indent=2)
        )
        return

    settings: dict[str, Any] = json.loads(
        settings_path.read_text()
    )  # lint-fixme: CheckUseOrjsonLoads

    if _has_custom_statusline(settings):
        return

    if settings.get("statusLine") != statusline_config:
        settings["statusLine"] = statusline_config
        settings_path.write_text(json.dumps(settings, indent=2))


if __name__ == "__main__":
    main()
