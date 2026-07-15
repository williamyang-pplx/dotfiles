---
name: error-review
description: Review code for real errors — logic bugs, unhandled edge cases, error-handling gaps, concurrency hazards, security issues. Reports verified findings with file:line and a suggested fix; skips style nits. Use when asked to review, check, or sanity-check code for mistakes.
---

# Review code for errors

Find real, verifiable errors in the target code. This is a correctness pass
only — no style or formatting feedback (that's format-code's job).

## Scope

1. If the request names files, a diff, or a PR, review that.
2. Otherwise review what changed in the working tree
   (`git diff HEAD` plus untracked source files).
3. Read enough surrounding code — callers, callees, type definitions — to
   judge each candidate finding in context, not just the changed lines.

## What to look for

- **Logic errors**: wrong operator or comparison, off-by-one, inverted
  condition, unreachable branches, incorrect boolean algebra.
- **Edge cases**: empty/None/null input, zero, negative numbers, unicode,
  duplicate keys, timezone/DST, first/last iteration.
- **Error handling**: swallowed exceptions, missing cleanup on the failure
  path, resource leaks (files, sockets, subprocesses), partial writes.
- **State and concurrency**: race conditions, check-then-act (TOCTOU),
  mutation of shared or default-arg state, ordering assumptions.
- **Interface misuse**: wrong argument order, misused API, mismatched types
  that the language won't catch, stale references after rename/refactor.
- **Security**: injection (shell, SQL, path), secrets in code or logs,
  unvalidated external input, unsafe deserialization.

## Verify before reporting

Adversarially check each candidate finding before including it: reread the
code assuming it is correct, and only report it if you can still articulate a
concrete input or sequence of events that triggers the failure. Drop anything
speculative — a short list of real bugs beats a long list of maybes.

## Report format

For each finding:

- `file:line` — one-line summary
- **Severity**: high (wrong result / crash / security) · medium (edge case)
  · low (latent hazard)
- **Why it's wrong**: the triggering input or scenario
- **Suggested fix**: concrete, minimal

Order findings by severity. Do not apply fixes unless asked. If nothing
survives verification, say "no issues found" plainly — do not pad the report.
