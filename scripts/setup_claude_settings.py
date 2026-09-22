#!/usr/bin/env python3
"""Merge personal Claude Code defaults into ~/.claude/settings.json.

Non-destructive: each setting is only written when absent, so values
customized directly on a machine (mac or devbox) survive re-provisioning.
Settings that are machine-specific (statusLine, env.BROWSER) are handled
elsewhere or left out on purpose — this is only for defaults that should
hold everywhere.

Current defaults:
  - permissions.defaultMode = bypassPermissions: sessions (and every fork/
    subagent they spawn, which inherit the session's mode) start without
    permission prompts.
  - skipDangerousModePermissionPrompt = true: suppresses the one-time
    bypass-mode acceptance dialog a fresh machine would otherwise show.
"""

import json
from pathlib import Path
from typing import Any


def main() -> None:
    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict[str, Any] = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())

    changed = False

    permissions = settings.setdefault("permissions", {})
    if "defaultMode" not in permissions:
        permissions["defaultMode"] = "bypassPermissions"
        changed = True

    if "skipDangerousModePermissionPrompt" not in settings:
        settings["skipDangerousModePermissionPrompt"] = True
        changed = True

    if changed:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")


if __name__ == "__main__":
    main()
