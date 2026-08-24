#!/usr/bin/env python3
"""Read Claude Code session transcripts (~/.claude/projects/**/*.jsonl).

Subcommands:
  list    List recent sessions (optionally across all projects) with title,
          first user prompt, message count, mtime, cwd, and session id.
  extract Emit a distilled, readable transcript for one session so it can be
          folded into the current conversation's context.

The JSONL schema is internal to Claude Code and can change between versions,
so every field access here is defensive: unknown entry types are skipped and
missing keys degrade gracefully instead of crashing.
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")


def cwd_to_project_dir(cwd):
    """Claude Code encodes the cwd by replacing non-alphanumerics with '-'."""
    slug = "".join(c if c.isalnum() else "-" for c in cwd)
    return os.path.join(PROJECTS_DIR, slug)


def iter_entries(path):
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def text_from_content(content):
    """Message content is either a string or a list of typed parts."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    out = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            out.append(part.get("text", ""))
        elif ptype == "thinking":
            continue  # skip internal reasoning
        elif ptype == "tool_use":
            name = part.get("name", "tool")
            inp = part.get("input", {})
            summary = ""
            if isinstance(inp, dict):
                # Prefer the most human-meaningful field.
                for k in ("command", "description", "prompt", "file_path", "pattern", "query"):
                    if inp.get(k):
                        summary = str(inp[k])
                        break
            out.append(f"[tool:{name}] {summary}".rstrip())
        elif ptype == "tool_result":
            res = part.get("content", "")
            txt = text_from_content(res) if not isinstance(res, str) else res
            snippet = txt.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:300] + " …"
            out.append(f"[tool_result] {snippet}")
    return "\n".join(s for s in out if s.strip())


def scan_session(path):
    """Return metadata about a session file without loading it all into memory twice."""
    meta = {
        "path": path,
        "session_id": os.path.splitext(os.path.basename(path))[0],
        "title": None,
        "first_user": None,
        "cwd": None,
        "git_branch": None,
        "user_msgs": 0,
        "assistant_msgs": 0,
        "last_ts": None,
    }
    for o in iter_entries(path):
        t = o.get("type")
        if t == "ai-title" and not meta["title"]:
            meta["title"] = o.get("aiTitle") or o.get("title")
        if t == "summary" and not meta["title"]:
            meta["title"] = o.get("summary")
        if meta["cwd"] is None and o.get("cwd"):
            meta["cwd"] = o.get("cwd")
        if meta["git_branch"] is None and o.get("gitBranch"):
            meta["git_branch"] = o.get("gitBranch")
        if o.get("timestamp"):
            meta["last_ts"] = o.get("timestamp")
        if t == "user":
            msg = o.get("message", {}) or {}
            txt = text_from_content(msg.get("content", "")).strip()
            # Skip harness/local-command noise for the "first real prompt" hint.
            if txt and not txt.startswith("<") and not txt.startswith("Caveat:"):
                meta["user_msgs"] += 1
                if meta["first_user"] is None:
                    meta["first_user"] = txt[:160].replace("\n", " ")
        elif t == "assistant":
            meta["assistant_msgs"] += 1
    return meta


def fmt_mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return "?"


def cmd_list(args):
    if args.all_projects:
        pattern = os.path.join(PROJECTS_DIR, "*", "*.jsonl")
    elif args.cwd:
        pattern = os.path.join(cwd_to_project_dir(args.cwd), "*.jsonl")
    else:
        pattern = os.path.join(cwd_to_project_dir(os.getcwd()), "*.jsonl")
    files = glob.glob(pattern)
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    files = files[: args.limit]
    if not files:
        print(f"No sessions found for pattern: {pattern}", file=sys.stderr)
        return 1
    for i, path in enumerate(files):
        m = scan_session(path)
        title = m["title"] or m["first_user"] or "(untitled)"
        print(f"#{i}  {fmt_mtime(path)}  [{m['user_msgs']}u/{m['assistant_msgs']}a]  {m['session_id']}")
        print(f"    title : {title}")
        if m["cwd"]:
            branch = f" ({m['git_branch']})" if m["git_branch"] else ""
            print(f"    cwd   : {m['cwd']}{branch}")
        if m["first_user"] and m["first_user"] != title:
            print(f"    first : {m['first_user']}")
    return 0


def resolve_path(ident, cwd=None):
    """Resolve a session id, partial id, absolute path, or list index to a file path."""
    if os.path.isfile(ident):
        return ident
    search_dirs = [cwd_to_project_dir(cwd)] if cwd else []
    search_dirs += glob.glob(os.path.join(PROJECTS_DIR, "*"))
    candidates = []
    for d in search_dirs:
        candidates.extend(glob.glob(os.path.join(d, "*.jsonl")))
    # exact id match
    for p in candidates:
        if os.path.splitext(os.path.basename(p))[0] == ident:
            return p
    # partial id prefix match
    matches = [p for p in candidates if os.path.basename(p).startswith(ident)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit(f"Ambiguous session id '{ident}' matches {len(matches)} files.")
    raise SystemExit(f"No session found for '{ident}'.")


def cmd_extract(args):
    path = resolve_path(args.session, cwd=args.cwd)
    meta = scan_session(path)
    print(f"# Imported session: {meta['title'] or '(untitled)'}")
    print(f"- session id: {meta['session_id']}")
    if meta["cwd"]:
        print(f"- cwd: {meta['cwd']}" + (f" (branch {meta['git_branch']})" if meta['git_branch'] else ""))
    print(f"- messages: {meta['user_msgs']} user / {meta['assistant_msgs']} assistant")
    print(f"- last activity: {fmt_mtime(path)}")
    print()
    print("---")
    print()
    turn = 0
    for o in iter_entries(path):
        t = o.get("type")
        if t not in ("user", "assistant"):
            continue
        msg = o.get("message", {}) or {}
        txt = text_from_content(msg.get("content", "")).strip()
        if not txt:
            continue
        # Drop harness-injected caveats/system-reminder noise from user turns.
        if t == "user" and (txt.startswith("<local-command") or txt.startswith("Caveat:") or txt.startswith("<command-")):
            continue
        role = "USER" if t == "user" else "ASSISTANT"
        if args.max_chars and len(txt) > args.max_chars:
            txt = txt[: args.max_chars] + "\n… [truncated]"
        turn += 1
        print(f"## [{role}]")
        print(txt)
        print()
    if turn == 0:
        print("(no readable user/assistant turns found — schema may have changed)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="list recent sessions")
    pl.add_argument("--limit", type=int, default=15)
    pl.add_argument("--all-projects", action="store_true", help="scan every project, not just cwd's")
    pl.add_argument("--cwd", help="project cwd to scan (default: current dir)")
    pl.set_defaults(func=cmd_list)

    pe = sub.add_parser("extract", help="emit a distilled transcript for one session")
    pe.add_argument("session", help="session id, partial id, or path to .jsonl")
    pe.add_argument("--cwd", help="project cwd to disambiguate the session id")
    pe.add_argument("--max-chars", type=int, default=4000, help="truncate each turn (0 = no limit)")
    pe.set_defaults(func=cmd_extract)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
