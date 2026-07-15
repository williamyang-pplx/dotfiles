---
name: format-code
description: Reformat code to William's personal style preferences (naming, structure, comments, language idioms). Use when asked to format, restyle, or clean up the style of code. Style-only — never changes behavior; use error-review for bug hunting.
---

# Format code to personal style

Apply the style preferences below to the target code. This is a style-only
pass: never change behavior, public APIs, or logic.

## Scope

1. If the request names files, format those.
2. Otherwise format what changed in the working tree
   (`git diff --name-only HEAD` plus untracked source files).
3. Never reformat vendored, generated, or third-party code.

## Ground rules

- **Project config wins.** If the repo configures a formatter or linter
  (.editorconfig, ruff, black, prettier, eslint, gofmt, rustfmt, ...), run that
  tool and keep its output. Apply the personal preferences below only where the
  tool leaves room (naming, structure, comments).
- Behavior-preserving only. If you spot a bug while formatting, list it at the
  end for follow-up — do not fix it in this pass (that's error-review's job).
- Keep diffs minimal: restyle the code in scope, don't reflow untouched files.

## Style preferences

<!-- Personal preferences — edit this section to taste. -->

### All languages

- Max line length ~100.
- Prefer early returns / guard clauses over nested conditionals.
- Descriptive names over abbreviations; no single-letter names outside tiny
  loop/lambda scopes.
- Comments explain *why*, not *what*. Delete commented-out code and stale
  TODOs; keep comment density consistent with the surrounding file.
- One blank line between logical blocks; no runs of multiple blank lines.

### Python

- 4-space indent, double quotes, f-strings over `%`/`.format()`.
- Type hints on public function signatures.
- `pathlib.Path` over `os.path`; context managers over manual open/close.
- Imports grouped stdlib / third-party / local, alphabetized within groups.

### TypeScript / JavaScript

- 2-space indent, prettier-style defaults (semicolons, double quotes).
- `const` by default; `async`/`await` over `.then()` chains.
- Explicit return types on exported functions.

### Bash

- `#!/usr/bin/env bash` + `set -euo pipefail` in scripts.
- 2-space indent, `[[ ]]` over `[ ]`, quote all expansions.
- UPPER_CASE for script-level constants, lower_case for locals and loop vars.
- Must pass `bash -n`; fix anything shellcheck would flag while you're there.

## After formatting

- Re-run the project formatter/linter (or a syntax check like `bash -n` /
  `python -m py_compile`) on every touched file to confirm nothing broke.
- Summarize what was restyled per file, and list any suspected bugs noticed
  along the way as follow-ups.
