---
name: format-code
description: Reformat code to William's personal style preferences (naming, structure, comments, language idioms). Use when asked to format, restyle, or clean up the style of code. Style-only — never changes behavior; use error-review for bug hunting.
---

# Format code to personal style

Apply the style preferences below to the target code. This is a style-only
pass: never change behavior, public APIs, or logic.

## Sync with main before editing

Before making any code changes, pull the latest main and rebase the PR branch
onto it:

1. `git fetch origin main` (or the repo's default branch).
2. `git rebase origin/main` on the current PR branch.
3. If the rebase hits conflicts, stop immediately — do not resolve, `--abort`,
   or `--continue` yourself. Conflicts are handled manually by the user; tell
   them what conflicted and wait.

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

### Comments
- Never write comments unless the user actively instructs you to add a comment. Comments
include doc strings for files, classes, and functions.

### Test Writing
- Always prefer to write limited tests that cover the most important cases, rather than exhuastive
testing that covers every single edge case.
- In single tests always try to exhuastively cover as many cases as possible so as not to have to write
multiple tests for each individual case. 
- Always avoid writing explanatory comments for tests. Instead prefer descriptive variable names
and functions that explain what's being tested clearly. 

### Imports
- No lazy imports! Imports should always live at the top of their source file.

### All languages

- Max line length ~100.
- Prefer early returns / guard clauses over nested conditionals.
- Descriptive names over abbreviations; no single-letter names outside tiny
  loop/lambda scopes.

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
- If the restyled code is pushed to a PR, automatically update the PR
  description: invoke the /pr-description skill at the end so the description
  reflects the updated diff.
