#!/usr/bin/env python3
"""Prefetch everything a PR-review workflow needs and emit a ready-to-run script.

Usage: prefetch.py <pr-number|url> [skill-md-path] [--template deep|quick] [--since SHA] [--fresh]

Run from inside the PR's repo. Fetches the PR head, diffs it locally (no
GitHub diff-size or 100-file limits), pulls every existing comment, checks
whether the PR is the current user's own, and splits the deep-review skill's
rubric into per-agent sections. Those inputs, plus review-lib.js, are inlined
into a per-run copy of the template (deep-review-pr.js or quick-review-pr.js)
so subagents start reviewing on their first turn instead of spending turns on
gh/Read. Prints the generated script's path.

The quick template also gets the context deep-review's lens agents would have
gathered, done here in seconds: the changed files at head, call sites of the
changed symbols, and the AGENTS.md/CLAUDE.md files on the touched paths. When
an earlier review of the same PR saved a result.json, quick re-reviews only
the changes since then and rechecks that review's findings.
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
# Must match the line in each template exactly.
PLACEHOLDER = "const INPUTS = null  // @prefetch"
HERE = Path(__file__).resolve().parent
LIB = HERE / "review-lib.js"
TEMPLATES = {
    "deep": ("deep-review-pr", HERE / "deep-review-pr.js"),
    "quick": ("quick-review-pr", HERE.parent / "quick-review" / "quick-review-pr.js"),
}
# Quick context caps: inline the changed files' full text up to this many
# characters (else agents read <ctx>/head/<path>), and bound the call-site and
# docs sections so one huge PR can't blow up every prompt.
INLINE_CONTEXT_CHARS = 150_000
MAX_SYMBOLS = 40
MAX_SITES_PER_SYMBOL = 15
MAX_DOCS_CHARS = 60_000
MAX_PRIOR_LENS_CHARS = 15_000
# Definitions on added or removed diff lines whose call sites the quick
# reviewers should see: def/class/fn/func/struct/... and module-level CONSTANTS.
SYMBOL_RE = re.compile(
    r"^[+-]\s*(?:export\s+)?(?:pub(?:\([\w:]+\))?\s+)?(?:async\s+)?"
    r"(?:def|class|function|fn|func|struct|enum|trait|interface|type)\s+([A-Za-z_]\w*)"
    r"|^[+-]([A-Z][A-Z0-9_]{2,})\s*[:=]"
)
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
        "number,title,body,url,author,headRefOid,baseRefName,baseRefOid,commits",
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


def diff_files(base: str, head: str, paths: list[str] | None = None) -> list[dict]:
    """[{path, changes, old}] from `git diff --numstat -z`; binary files are skipped."""
    out = run("git", "diff", "--numstat", "-z", "-M", base, head, *(["--", *paths] if paths else []))
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


def write_patches(base: str, head: str, files: list[dict], ctx: Path) -> dict[str, str]:
    ctx.mkdir(parents=True, exist_ok=True)
    (ctx / "diff.patch").write_text(run("git", "diff", "-M", base, head, "--", *[f["path"] for f in files]))
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


def try_run(*cmd: str) -> str | None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def head_files(head: str, files: list[dict], ctx: Path) -> dict[str, str] | None:
    """Changed files' full text at head, under <ctx>/head/; inlined when small. Deleted files are skipped."""
    contents = {}
    for f in files:
        text = try_run("git", "show", f"{head}:{f['path']}")
        if text is None:
            continue
        dest = ctx / "head" / f["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        contents[f["path"]] = text
    return contents if sum(len(t) for t in contents.values()) <= INLINE_CONTEXT_CHARS else None


def changed_symbols(patches: dict[str, str]) -> list[str]:
    seen: dict[str, None] = {}
    for patch in patches.values():
        for line in patch.splitlines():
            if line.startswith(("+++", "---")):
                continue
            match = SYMBOL_RE.match(line)
            name = match and (match.group(1) or match.group(2))
            if name and len(name) >= 3 and not name.startswith(("test", "__")):
                seen[name] = None
    return list(seen)[:MAX_SYMBOLS]


def call_sites(head: str, symbols: list[str]) -> str:
    """`git grep -w` hits for each symbol at head, capped per symbol."""
    def grep(symbol: str) -> str:
        out = try_run("git", "grep", "-n", "-w", "-I", "-F", "-e", symbol, head) or ""
        hits = [line.split(":", 1)[1][:200] for line in out.splitlines()]
        more = f"\n  ... {len(hits) - MAX_SITES_PER_SYMBOL} more" if len(hits) > MAX_SITES_PER_SYMBOL else ""
        return f"{symbol}:\n" + "\n".join(f"  {h}" for h in hits[:MAX_SITES_PER_SYMBOL]) + more
    with ThreadPoolExecutor() as pool:
        return "\n".join(pool.map(grep, symbols)) or "(no changed top-level symbols found)"


def agent_docs(head: str, files: list[dict]) -> str:
    """Every AGENTS.md/CLAUDE.md at head in a directory that contains a changed file."""
    tree = run("git", "ls-tree", "-r", "--name-only", head).splitlines()
    docs = [p for p in tree if os.path.basename(p) in ("AGENTS.md", "CLAUDE.md")]
    dirs = {os.path.dirname(p) for p in docs}
    touched = {d for d in dirs if any(d == "" or f["path"].startswith(d + "/") for f in files)}
    chosen = sorted((p for p in docs if os.path.dirname(p) in touched), key=lambda p: (p.count("/"), p))
    text = "\n\n".join(f"--- {p}\n{try_run('git', 'show', f'{head}:{p}') or ''}" for p in chosen)
    return text[:MAX_DOCS_CHARS] or "(none on the touched paths)"


def find_prior(common_dir: Path, number: int, exclude: Path, since: str | None) -> dict | None:
    """The newest saved review result for this PR (deep or quick), or the one at `since`."""
    root = common_dir / "deep-review"
    results = [r for pattern in (f"{number}-*/result.json", f"quick-{number}-*/result.json")
               for r in root.glob(pattern) if r.parent != exclude]
    prior = None
    for path in sorted(results, key=lambda r: r.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if since is None or data.get("headSha", "").startswith(since):
            prior = data
            break
    if prior is None:
        return {"kind": "manual", "headSha": since, "findings": [], "lensReports": {}} if since else None
    reports = {k: (v or "")[:MAX_PRIOR_LENS_CHARS] for k, v in (prior.get("lensReports") or {}).items()}
    return {
        "kind": prior.get("kind", "deep"),
        "headSha": prior.get("headSha"),
        "findings": prior.get("openFindings", prior.get("findings", [])),
        "lensReports": reports,
    }


def since_diff(prior_sha: str | None, head: str, pr_files: list[dict], tmp: Path, ctx: Path) -> dict | None:
    """The PR's files diffed from the last review's head to this one; None if that commit is gone.

    Patches are written under tmp/since but reported at ctx/since, where tmp is renamed to.
    """
    if not prior_sha or try_run("git", "cat-file", "-e", f"{prior_sha}^{{commit}}") is None:
        return None
    sha = run("git", "rev-parse", prior_sha).strip()
    if sha == head:
        return {"base": sha, "files": [], "patches": {}, "dir": str(ctx / "since")}
    files = diff_files(sha, head, [f["path"] for f in pr_files])
    patches = write_patches(sha, head, files, tmp / "since") if files else {}
    return {
        "base": sha,
        "files": [{"path": f["path"], "changes": f["changes"]} for f in files],
        "patches": patches if sum(f["changes"] for f in files) <= INLINE_DIFF_LINES else None,
        "dir": str(ctx / "since"),
    }


def build_run_script(template: Path, inputs: dict, out: Path) -> None:
    script = template.read_text()
    if script.count(PLACEHOLDER) != 1:
        sys.exit(f"prefetch: expected exactly one `{PLACEHOLDER}` in {template}")
    out.write_text(script.replace(PLACEHOLDER, f"const INPUTS = {json.dumps(inputs)}\n{LIB.read_text()}"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pr")
    parser.add_argument("skill_md", type=Path, nargs="?", default=HERE / "SKILL.md",
                        help="rubric source (default: deep-review's SKILL.md)")
    parser.add_argument("--template", choices=TEMPLATES, default="deep")
    parser.add_argument("--since", help="quick only: re-review the changes since this commit")
    parser.add_argument("--fresh", action="store_true", help="quick only: ignore earlier reviews")
    args = parser.parse_args()
    workflow, template = TEMPLATES[args.template]

    meta = pr_meta(args.pr)
    common_dir = Path(os.path.abspath(run("git", "rev-parse", "--git-common-dir").strip()))
    prefix = "quick-" if args.template == "quick" else ""
    ctx = common_dir / "deep-review" / f"{prefix}{meta['number']}-{meta['headRefOid'][:12]}"
    tmp = ctx.with_name(ctx.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    with ThreadPoolExecutor() as pool:
        head = pool.submit(fetch_head, meta)
        comments = pool.submit(fetch_comments, meta)
        rubric = pool.submit(split_rubric, args.skill_md)
        viewer = pool.submit(run, "gh", "api", "user", "-q", ".login")
        head.result()
        files = diff_files(meta["mergeBase"], meta["headRefOid"])
        patches = write_patches(meta["mergeBase"], meta["headRefOid"], files, tmp)
        inputs = {
            "workflow": workflow,
            "pr": meta["number"],
            "author": meta["author"]["login"],
            "mine": meta["author"]["login"] == viewer.result().strip(),
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
        if args.template == "quick":
            head_sha = meta["headRefOid"]
            prior = None if args.fresh else find_prior(common_dir, meta["number"], ctx, args.since)
            sites = pool.submit(call_sites, head_sha, changed_symbols(patches))
            docs = pool.submit(agent_docs, head_sha, files)
            inputs["context"] = {
                "files": head_files(head_sha, files, tmp),
                "headDir": str(ctx / "head"),
                "callSites": sites.result(),
                "docs": docs.result(),
            }
            inputs["prior"] = prior
            inputs["since"] = since_diff(prior["headSha"], head_sha, files, tmp, ctx) if prior else None

    build_run_script(template, inputs, tmp / "run.js")
    shutil.rmtree(ctx, ignore_errors=True)
    tmp.rename(ctx)
    print(ctx / "run.js")


if __name__ == "__main__":
    main()
