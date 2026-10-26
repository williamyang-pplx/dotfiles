#!/usr/bin/env python3
"""Helper CLI for the low-level-plan skill. Run from inside the target repo.

  llp.py context --area NAME=PATH[,PATH...] [...] [--plan-file F]   gather the planning context; print a digest
  llp.py outline PATH [...]                                          symbol outline of files or dirs, at file:line
  llp.py callers SYMBOL [--in FILE]                                  where a symbol is used outside its file
  llp.py threads PATH --ctx DIR [--reviewer LOGIN]                   past human review threads on a path
  llp.py check PLAN.md [--ctx DIR] [--resolutions FILE]              sweep the plan; exit 0 only when clean
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import repo as rp


def outline(paths: list[str]) -> None:
    repo = rp.repo_top()
    for rel in rp.tracked(repo, *paths):
        count, symbols = rp.outline_file(repo, rel)
        print(f"### {rel} ({count} lines)" + "".join(f"\n  {s}" for s in symbols))


def callers(name: str, defined_in: str | None) -> None:
    repo = rp.repo_top()
    defs = {(p, n) for p, n, _ in rp.definitions(repo, name)}
    scope = set(rp.file_importers(repo, defined_in)) if defined_in else None
    for path, number, text in rp.symbol_mentions(repo, name):
        if (path, number) in defs or path == defined_in or (scope is not None and path not in scope):
            continue
        print(f"{path}:{number}: {text.strip()[:160]}")
    for path, number in sorted(defs):
        print(f"(defined at {path}:{number})")


def threads(path: str, ctx_dir: Path, reviewer: str | None) -> None:
    import reviews

    ctx = json.loads((ctx_dir / "context.json").read_text())
    shown = 0
    for pr in ctx["prs"]:
        for thread in pr["threads"]:
            if not rp.in_area(thread["path"], [path]):
                continue
            if reviewer and not any(c["author"] == reviewer for c in thread["comments"]):
                continue
            print("\n".join(reviews.render_thread(thread, f" (PR #{pr['number']}: {pr['title']}, @{pr['author']})")))
            shown += 1
    print(f"llp threads: {shown} thread(s) on {path}" + (f" with {reviewer}" if reviewer else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    ctx_cmd = commands.add_parser("context", help="gather the planning context for the plan's areas")
    ctx_cmd.add_argument("--area", action="append", required=True, help="NAME=PATH[,PATH...], repo-relative")
    ctx_cmd.add_argument("--plan-file", type=Path, help="high-level plan, for ticket IDs (default: none)")
    outline_cmd = commands.add_parser("outline", help="symbol outline of files or dirs")
    outline_cmd.add_argument("paths", nargs="+")
    callers_cmd = commands.add_parser("callers", help="where a symbol is used")
    callers_cmd.add_argument("symbol")
    callers_cmd.add_argument("--in", dest="defined_in", help="file defining it: only list its importers' uses")
    threads_cmd = commands.add_parser("threads", help="past human review threads on a path")
    threads_cmd.add_argument("path")
    threads_cmd.add_argument("--ctx", type=Path, required=True)
    threads_cmd.add_argument("--reviewer")
    check_cmd = commands.add_parser("check", help="sweep a low-level plan")
    check_cmd.add_argument("plan", type=Path)
    check_cmd.add_argument("--ctx", type=Path, help="the `llp context` dir, enabling convention/review/open-PR checks")
    check_cmd.add_argument("--resolutions", type=Path, help="file of `<id> <justification>` lines")
    args = parser.parse_args()

    if args.command == "context":
        import context

        context.build(args.area, args.plan_file.read_text() if args.plan_file else "")
    elif args.command == "outline":
        outline(args.paths)
    elif args.command == "callers":
        callers(args.symbol, args.defined_in)
    elif args.command == "threads":
        threads(args.path, args.ctx, args.reviewer)
    else:
        import plancheck

        sys.exit(plancheck.check(args.plan, args.resolutions, args.ctx))


if __name__ == "__main__":
    main()
