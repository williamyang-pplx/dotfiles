#!/usr/bin/env python3
"""Prefetch everything the deep-review-pr workflow needs and emit a ready-to-run script.

Usage: prefetch.py <pr-number|url> <mine|other> <skill-md-path>

Run from inside the PR's repo. Fetches the PR head, diffs it locally (no
GitHub diff-size or 100-file limits), pulls every existing comment, and splits
the skill's rubric into per-agent sections. Those inputs are inlined into a
per-run copy of deep-review-pr.js so subagents start reviewing on their first
turn instead of spending turns on gh/Read. Prints the generated script's path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Inline patches into agent prompts when the PR's total changed lines are at
# or below this; above it, agents read files/<path>.patch from the ctx dir.
INLINE_DIFF_LINES = 2000
# Must match the line in deep-review-pr.js exactly.
PLACEHOLDER = "const INPUTS = null  // @prefetch"
# Existing comments are context for duplicate detection, not review material.
MAX_COMMENT_CHARS = 1500

THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          isResolved isOutdated path line originalLine
          comments(first: 50) { nodes { author { login } body } }
        }
      }
    }
  }
}
"""


def run(*cmd: str) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"prefetch: `{' '.join(cmd[:4])} ...` failed:\n{result.stderr.strip()}")
    return result.stdout


def parse_json_stream(text: str) -> list:
    """`gh api --paginate` emits one JSON document per page, concatenated."""
    decoder, docs, i = json.JSONDecoder(), [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        doc, i = decoder.raw_decode(text, i)
        docs.append(doc)
    return docs


def pr_meta(pr: str) -> dict:
    meta = json.loads(run(
        "gh", "pr", "view", pr, "--json",
        "number,title,body,url,headRefOid,baseRefName,baseRefOid,commits",
    ))
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/\d+", meta["url"])
    if not match:
        sys.exit(f"prefetch: can't parse owner/repo from {meta['url']}")
    meta["owner"], meta["repo"] = match.groups()

    remotes = run("git", "remote", "-v")
    if f"/{meta['repo']}" not in remotes and f":{meta['repo']}" not in remotes:
        sys.exit(f"prefetch: run this from a checkout of {meta['owner']}/{meta['repo']} (cwd remotes don't match)")
    return meta


def fetch_head(meta: dict) -> None:
    """Fetch from the PR's repo URL, not origin — origin may be a fork."""
    refspecs = (f"+refs/pull/{meta['number']}/head", f"+refs/heads/{meta['baseRefName']}")
    url = f"https://github.com/{meta['owner']}/{meta['repo']}.git"
    fetched = subprocess.run(["git", "fetch", "-q", url, *refspecs], capture_output=True)
    if fetched.returncode != 0:
        run("git", "fetch", "-q", "origin", *refspecs)
    run("git", "cat-file", "-e", meta["headRefOid"])
    meta["mergeBase"] = run("git", "merge-base", meta["baseRefOid"], meta["headRefOid"]).strip()


def diff_files(meta: dict) -> list[dict]:
    """[{path, changes, old}] from `git diff --numstat -z`; binary files are skipped."""
    out = run("git", "diff", "--numstat", "-z", "-M", meta["mergeBase"], meta["headRefOid"])
    fields, files, i = out.split("\0"), [], 0
    while i < len(fields) and fields[i]:
        added, deleted, path = fields[i].split("\t", 2)
        old = None
        if path == "":  # rename: "<a>\t<d>\t\0<old>\0<new>\0"
            old, path = fields[i + 1], fields[i + 2]
            i += 3
        else:
            i += 1
        if added == "-":
            continue
        files.append({"path": path, "changes": int(added) + int(deleted), "old": old})
    return files


def write_patches(meta: dict, files: list[dict], ctx: Path) -> dict[str, str]:
    base, head = meta["mergeBase"], meta["headRefOid"]
    (ctx / "diff.patch").write_text(run("git", "diff", "-M", base, head))
    patches = {}
    for f in files:
        paths = [f["old"], f["path"]] if f["old"] else [f["path"]]
        patch = run("git", "diff", "-M", base, head, "--", *paths)
        dest = ctx / "files" / f"{f['path']}.patch"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(patch)
        patches[f["path"]] = patch
    return patches


def fetch_comments(meta: dict) -> dict[str, list[dict]]:
    """Every existing comment, grouped by file path ("" = PR-level). Always refetched."""
    owner, repo, number = meta["owner"], meta["repo"], meta["number"]
    by_path: dict[str, list[dict]] = {}

    def add(path: str, author: str, body: str, **extra) -> None:
        if body.strip():
            by_path.setdefault(path, []).append({"author": author, "body": body[:MAX_COMMENT_CHARS], **extra})

    threads = run(
        "gh", "api", "graphql", "--paginate",
        "-f", f"owner={owner}", "-f", f"name={repo}", "-F", f"number={number}",
        "-f", f"query={THREADS_QUERY}",
    )
    for page in parse_json_stream(threads):
        for t in page["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]:
            comments = t["comments"]["nodes"]
            if not comments:
                continue
            body = "\n---\n".join(f"{(c['author'] or {}).get('login', '?')}: {c['body']}" for c in comments)
            add(t["path"], (comments[0]["author"] or {}).get("login", "?"), body,
                line=t["line"] or t["originalLine"], resolved=t["isResolved"], outdated=t["isOutdated"])

    for endpoint in (f"repos/{owner}/{repo}/pulls/{number}/reviews", f"repos/{owner}/{repo}/issues/{number}/comments"):
        for page in parse_json_stream(run("gh", "api", "--paginate", endpoint)):
            for c in page:
                add("", (c.get("user") or {}).get("login", "?"), c.get("body") or "")
    return by_path


def split_rubric(skill_md: Path) -> dict:
    """Split SKILL.md into the sections each agent needs, keyed for deep-review-pr.js."""
    sections, current = {}, None
    for line in skill_md.read_text().splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    text = {name: f"## {name}\n" + "\n".join(lines).strip() for name, lines in sections.items()}

    def find(prefix: str) -> str | None:
        return next((name for name in text if name.startswith(prefix)), None)

    missing = [p for p in ("Gather context", "Axis 1", "Verify before reporting", "Report") if not find(p)]
    if missing:
        sys.exit(f"prefetch: {skill_md} is missing sections: {', '.join(missing)}")

    lens, label = {}, None
    for line in sections[find("Gather context")]:
        bullet = re.match(r"\s*- \*\*(.+?)\*\*", line)
        if bullet:
            label = bullet.group(1)
            lens[label] = [line.strip()]
        elif re.match(r"\d+\.", line):
            label = None
        elif label and line.strip():
            lens[label].append(line.strip())

    axis = {}
    for name in text:
        match = re.match(r"Axis (\d+):", name)
        if match:
            axis[match.group(1)] = text[name]

    helper = find("Helper placement")
    return {
        "lens": {k: " ".join(v) for k, v in lens.items()},
        "axis": axis,
        "verify": text[find("Verify before reporting")],
        "helper": text[helper] if helper else "",
        "report": text[find("Report")],
    }


def build_run_script(template: Path, inputs: dict, out: Path) -> None:
    script = template.read_text()
    if script.count(PLACEHOLDER) != 1:
        sys.exit(f"prefetch: expected exactly one `{PLACEHOLDER}` in {template}")
    out.write_text(script.replace(PLACEHOLDER, f"const INPUTS = {json.dumps(inputs)}"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pr")
    parser.add_argument("mode", choices=["mine", "other"])
    parser.add_argument("skill_md", type=Path)
    args = parser.parse_args()

    meta = pr_meta(args.pr)
    common_dir = Path(os.path.abspath(run("git", "rev-parse", "--git-common-dir").strip()))
    ctx = common_dir / "deep-review" / f"{meta['number']}-{meta['headRefOid'][:12]}"
    tmp = ctx.with_name(ctx.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    with ThreadPoolExecutor() as pool:
        head = pool.submit(fetch_head, meta)
        comments = pool.submit(fetch_comments, meta)
        rubric = pool.submit(split_rubric, args.skill_md)
        head.result()
        files = diff_files(meta)
        patches = write_patches(meta, files, tmp)
        inputs = {
            "pr": meta["number"],
            "mode": args.mode,
            "headSha": meta["headRefOid"],
            "ctxDir": str(ctx),
            "repoDir": run("git", "rev-parse", "--show-toplevel").strip(),
            "description": "\n\n".join([
                meta["title"],
                meta["body"] or "(no description)",
                "Commits:\n" + "\n".join(f"- {c['messageHeadline']}" for c in meta["commits"]),
            ]),
            "files": [{"path": f["path"], "changes": f["changes"]} for f in files],
            "patches": patches if sum(f["changes"] for f in files) <= INLINE_DIFF_LINES else None,
            "comments": comments.result(),
            "rubric": rubric.result(),
        }

    build_run_script(Path(__file__).resolve().with_name("deep-review-pr.js"), inputs, tmp / "run.js")
    shutil.rmtree(ctx, ignore_errors=True)
    tmp.rename(ctx)
    print(ctx / "run.js")


if __name__ == "__main__":
    main()
