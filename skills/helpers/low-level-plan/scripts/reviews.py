"""GitHub facts for low-level-plan: past PR review threads, open PRs, reviewer profiles, ticket IDs.

All calls go through `gh`; every one degrades to "no data" instead of failing the run.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from repo import clip, in_area, run

MAX_OPEN_PRS = 200
MAX_OPEN_HITS = 15
MAX_PROFILE_PRS = 15
MAX_PROFILE_COMMENTS = 40
MAX_TICKETS = 20
MAX_COMMENT_CHARS = 1200
MAX_HUNK_CHARS = 800
MAX_PR_BODY_CHARS = 1500

# Review-bot accounts that GitHub reports as regular users.
BOT_LOGINS = {"pplx-bot", "copilot", "copilot-pull-request-reviewer", "linear"}
TICKET = re.compile(r"\b([A-Z][A-Z0-9]{1,5}-\d{1,6})\b")
LINEAR_URL = re.compile(r"linear\.app/[^/\s]+/issue/([A-Z][A-Z0-9]{1,5}-\d{1,6})")
# Uppercase-dash-number tokens that are never Linear tickets.
NOT_TICKETS = {"UTF", "SHA", "ISO", "RFC", "HTTP", "TLS", "FP", "BF", "INT", "CVE", "GPT", "PEP", "PR", "GH", "FIX"}

THREAD_FIELDS = """
          path line originalLine isResolved isOutdated
          comments(first: 20) { nodes { author { __typename login } body diffHunk } }
"""
PR_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number title url body state mergedAt headRefName
      author { login }
      reviewThreads(first: 100) { nodes { %s } }
      reviews(first: 50) { nodes { author { __typename login } body state } }
      comments(first: 50) { nodes { author { __typename login } body } }
    }
  }
}
""" % THREAD_FIELDS
PROFILE_QUERY = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: %d) {
    nodes { ... on PullRequest { number title url reviewThreads(first: 60) { nodes { %s } } } }
  }
}
""" % (MAX_PROFILE_PRS, THREAD_FIELDS)


def github_repo() -> tuple[str, str] | None:
    out = run("gh", "repo", "view", "--json", "owner,name", check=False)
    if not out:
        return None
    data = json.loads(out)
    return data["owner"]["login"], data["name"]


def viewer_login() -> str:
    return run("gh", "api", "user", "--jq", ".login", check=False).strip()


def graphql(query: str, **variables: str | int) -> dict | None:
    args = [x for k, v in variables.items() for x in ("-F" if isinstance(v, int) else "-f", f"{k}={v}")]
    out = run("gh", "api", "graphql", *args, "-f", f"query={query}", check=False)
    return json.loads(out)["data"] if out else None


def is_bot(author: dict | None) -> bool:
    if not author:
        return True
    login = author.get("login", "")
    return author.get("__typename") == "Bot" or login.endswith("[bot]") or login.lower() in BOT_LOGINS


def prs_for_commits(owner: str, name: str, commits: list[dict], pool: ThreadPoolExecutor) -> list[int]:
    """PR numbers behind the commits, newest first — from "(#123)" subjects, else the commits/pulls API."""
    def lookup(commit: dict) -> int | None:
        if commit["pr"]:
            return commit["pr"]
        out = run("gh", "api", f"repos/{owner}/{name}/commits/{commit['sha']}/pulls", "--jq", ".[0].number", check=False)
        return int(out) if out.strip().isdigit() else None

    return list(dict.fromkeys(number for number in pool.map(lookup, commits) if number))


def human_threads(nodes: list[dict], prefixes: list[str], *, pr_author: str = "", reviewer: str = "") -> list[dict]:
    """Review threads with human input, each with the diff hunk the thread was left on.

    With pr_author: threads someone other than the author joined. With reviewer:
    threads that reviewer commented on, keeping only their comments.
    """
    threads = []
    for thread in nodes:
        comments = [c for c in thread["comments"]["nodes"] if c["body"].strip() and not is_bot(c["author"])]
        if reviewer:
            comments = [c for c in comments if c["author"]["login"] == reviewer]
        if not any(c["author"]["login"] != pr_author for c in comments):
            continue
        hunk = next((c["diffHunk"] for c in thread["comments"]["nodes"] if c.get("diffHunk")), "")
        threads.append({
            "path": thread["path"], "line": thread["line"] or thread["originalLine"], "resolved": thread["isResolved"],
            # Outdated = the commented code changed afterwards: usually the comment was acted on.
            "outdated": thread["isOutdated"], "inArea": in_area(thread["path"], prefixes),
            "hunk": hunk[-MAX_HUNK_CHARS:],
            "comments": [{"author": c["author"]["login"], "body": clip(c["body"].strip(), MAX_COMMENT_CHARS)}
                         for c in comments],
        })
    return threads


def fetch_pr(owner: str, name: str, number: int, prefixes: list[str]) -> dict | None:
    data = graphql(PR_QUERY, owner=owner, name=name, number=number)
    pr = data and data["repository"]["pullRequest"]
    if not pr:
        return None
    author = (pr["author"] or {}).get("login", "?")
    general = [
        {"author": c["author"]["login"], "body": clip(c["body"].strip(), MAX_COMMENT_CHARS)}
        for c in pr["reviews"]["nodes"] + pr["comments"]["nodes"]
        if c["body"].strip() and not is_bot(c["author"]) and c["author"]["login"] != author
    ]
    return {
        "number": pr["number"], "title": pr["title"], "url": pr["url"], "author": author, "state": pr["state"],
        "mergedAt": (pr["mergedAt"] or "")[:10], "branch": pr["headRefName"],
        "body": clip(pr["body"] or "", MAX_PR_BODY_CHARS),
        "threads": human_threads(pr["reviewThreads"]["nodes"], prefixes, pr_author=author), "general": general,
    }


def render_thread(thread: dict, tag: str = "") -> list[str]:
    flags = "".join(f" [{flag}]" for flag, on in (("resolved", thread["resolved"]),
                                                  ("code changed after", thread["outdated"])) if on)
    lines = [f"## {thread['path']}:{thread['line']}{tag}{flags}"]
    if thread["hunk"]:
        lines += ["```diff", thread["hunk"].rstrip(), "```"]
    return lines + [f"- **{c['author']}**: {c['body']}" for c in thread["comments"]] + [""]


def render_pr(pr: dict) -> str:
    status = f"merged {pr['mergedAt']}" if pr["mergedAt"] else pr["state"].lower()
    lines = [f"# PR #{pr['number']}: {pr['title']}", f"{pr['url']} — by {pr['author']}, {status}", "",
             pr["body"].strip() or "(no description)", ""]
    for thread in sorted(pr["threads"], key=lambda t: not t["inArea"]):
        lines += render_thread(thread, "" if thread["inArea"] else " (outside the plan's area)")
    if pr["general"]:
        lines.append("## Review summaries and PR-level comments")
        lines += [f"- **{c['author']}**: {c['body']}" for c in pr["general"]]
    return "\n".join(lines).strip() + "\n"


def open_prs(prefixes: list[str]) -> list[dict]:
    out = run("gh", "pr", "list", "--state", "open", "--limit", str(MAX_OPEN_PRS), "--search", "sort:updated-desc",
              "--json", "number,title,url,author,files,isDraft", check=False)
    hits = []
    for pr in json.loads(out) if out else []:
        touched = [f["path"] for f in pr.get("files") or [] if in_area(f["path"], prefixes)]
        if touched:
            hits.append({"number": pr["number"], "title": pr["title"], "url": pr["url"],
                         "author": (pr["author"] or {}).get("login", "?"), "draft": pr["isDraft"], "touched": touched})
    return hits[:MAX_OPEN_HITS]


def reviewer_profile(owner: str, name: str, login: str, skip: set[int]) -> str | None:
    """One reviewer's recent review comments across the repo, outside the PRs already mined."""
    data = graphql(PROFILE_QUERY, q=f"repo:{owner}/{name} is:pr reviewed-by:{login} -author:{login} sort:updated-desc")
    if not data:
        return None
    lines, count = [f"# Reviewer profile: {login}", f"Their review comments on recent PRs across {owner}/{name}.", ""], 0
    for pr in data["search"]["nodes"]:
        if not pr or pr["number"] in skip:
            continue
        for thread in human_threads(pr["reviewThreads"]["nodes"], [], reviewer=login):
            lines += render_thread(thread, f" (PR #{pr['number']}: {pr['title']})")
            count += 1
            if count >= MAX_PROFILE_COMMENTS:
                return "\n".join(lines)
    return "\n".join(lines) if count else None


def find_tickets(plan: str, prs: list[dict]) -> dict[str, list[str]]:
    """Linear-style ticket IDs → where they were referenced (plan first, then newest PRs).

    Bare IDs in PR titles and bodies are often model or version names (GLM-5), so
    those count only when their team prefix is confirmed by the plan, a
    linear.app link, or a branch name.
    """
    def ids(text: str) -> set[str]:
        return {t for t in TICKET.findall(text) if t.split("-")[0] not in NOT_TICKETS}

    found = {ticket: ["plan"] for ticket in sorted(ids(plan))}
    strong = {pr["number"]: set(LINEAR_URL.findall(pr["body"])) | ids(pr["branch"].upper()) for pr in prs}
    teams = {t.split("-")[0] for t in found} | {t.split("-")[0] for linked in strong.values() for t in linked}
    for pr in prs:
        loose = {t for t in ids(f"{pr['title']}\n{pr['body']}") if t.split("-")[0] in teams}
        for ticket in sorted(strong[pr["number"]] | loose):
            found.setdefault(ticket, []).append(f"#{pr['number']}")
    return dict(list(found.items())[:MAX_TICKETS])
