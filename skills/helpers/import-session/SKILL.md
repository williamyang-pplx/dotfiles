---
name: import-session
description: Import the context of ANOTHER past Claude Code session into the CURRENT running session, so this session "knows" what happened in the other one. Use when asked to pull in / import / bring over / load context from a different session (by id, title, or "the last one"). Not for resuming — this folds another session's transcript into the current conversation.
---

# Import another session's context into this one

Claude Code has no native way to merge one session into another (`--resume` /
`--continue` / `/resume` switch you *into* an old session; they don't pull it
*into* the current one). This skill reads another session's on-disk transcript,
distills it, and lands the result in the current conversation so the work can
continue here.

Transcripts live at `~/.claude/projects/<cwd-slug>/<session-id>.jsonl`, where
`<cwd-slug>` is the working directory with every non-alphanumeric character
replaced by `-`. The JSONL schema is internal to Claude Code, so always go
through the bundled parser rather than reading the raw files by hand.

The parser lives next to this file: `import_session.py` (in the skill dir).

## Steps

1. **Figure out which session to import.**
   - If the user gave a session id (full or a unique prefix), a `.jsonl` path,
     or a title, use it directly in step 3.
   - Otherwise list candidates and let the user pick. Default to the current
     project; add `--all-projects` if they might mean a session from a
     different repo/dir:

     ```bash
     python3 "$SKILL_DIR/import_session.py" list --limit 15
     python3 "$SKILL_DIR/import_session.py" list --all-projects --limit 25
     ```

     Show the numbered list (title, id, cwd, first prompt, mtime) and ask which
     one — unless the request already names it (e.g. "import the last session"
     → take `#0`; "import the AI-9583 session" → match the title/cwd).

2. **Don't import the current session into itself.** The current session id is
   available from the transcript path if you need to exclude it.

3. **Extract the distilled transcript.**

   ```bash
   python3 "$SKILL_DIR/import_session.py" extract <session-id-or-path>
   ```

   - Add `--cwd <dir>` if a bare id is ambiguous across projects.
   - Each turn is truncated to 4000 chars by default; pass `--max-chars 0` for
     the full text when the user wants everything, or a smaller number for a
     very long session.

4. **Fold it into the current context.** Read the extractor's output, then in
   your reply to the user write a concise briefing of the imported session:
   the goal, key decisions, files/commands touched, current state, and open
   threads. That briefing becomes part of this session's context, which is the
   whole point — the current session now "knows" the other one.

   - For a large session (e.g. the `extract` output is huge), summarize rather
     than pasting it verbatim; keep concrete identifiers (file paths, PR/ticket
     numbers, branch names, commands) since those are what future work needs.
   - If the extractor prints "no readable turns found", the schema may have
     changed — fall back to `claude -p --resume <id> --output-format json
     "summarize this session in detail"` and report that you used the fallback.

## Notes

- `$SKILL_DIR` is this skill's directory. If it isn't set, use the absolute
  path `~/Documents/dotfiles/skills/session/import-session`.
- This is read-only: it never modifies the other session or writes to disk.
- If the user wants the imported context to persist across future sessions
  (not just this one), offer to save the briefing to memory or `CLAUDE.md`.
