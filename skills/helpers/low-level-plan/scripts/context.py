"""`llp context`: gather everything the planner should know about the plan's areas into one directory.

Writes <git-common-dir>/low-level-plan/<head>-<digest>/ with areas/, prs/, profiles/,
docs.md, history.md, and context.json, then prints a digest pointing into it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import repo as rp
import reviews

MAX_PRS = 80
MAX_PROFILED_REVIEWERS = 3
MAX_IMPORTERS = 60
MAX_COCHANGE = 25
MAX_HOT_FILES = 15
DIGEST_IMPORTERS = 8
DIGEST_COCHANGE = 8


def parse_areas(specs: list[str]) -> list[dict]:
    areas = []
    for spec in specs:
        name, sep, paths = spec.partition("=")
        if not sep or not name.strip() or not paths.strip():
            raise SystemExit(f"llp: --area expects NAME=PATH[,PATH...], got {spec!r}")
        areas.append({"name": name.strip(), "paths": [p.strip().strip("/") for p in paths.split(",") if p.strip()]})
    return areas


def area_context(repo: Path, area: dict, anchored: dict[str, str], pool: ThreadPoolExecutor, warnings: list[str]) -> dict:
    paths = sorted({anchored[p] for p in area["paths"] if anchored[p]})
    base = {"name": area["name"], "paths": area["paths"], "anchors": paths}
    if not paths:
        return {**base, "files": [], "map": "(nothing tracked yet)", "importers": [], "cochange": [], "hot": [], "tests": ""}
    prefixes = sorted(set(paths) | {p for p in area["paths"] if anchored[p]})
    files, rendered = rp.code_map(repo, paths, pool, warnings)
    imports = rp.importers(repo, files, paths, prefixes)
    outside, hot = rp.cochange(repo, paths, prefixes)
    outside = [(f, n) for f, n in outside if n >= 2][:MAX_COCHANGE]
    return {
        **base,
        "files": files,
        "map": rendered,
        "importers": imports[:MAX_IMPORTERS],
        "importersDropped": max(0, len(imports) - MAX_IMPORTERS),
        "cochange": outside,
        "hot": hot[:MAX_HOT_FILES],
        "tests": rp.test_landscape(repo, files, [p for p, _ in imports] + [f for f, _ in outside], paths),
    }


def render_area(area: dict) -> str:
    importers = "\n".join(f"- {p} ← {', '.join(labels[:6])}" for p, labels in area["importers"]) or "(none found)"
    if area.get("importersDropped"):
        importers += f"\n- … {area['importersDropped']} more importers not listed"
    cochange = "\n".join(f"- {f} ({n} shared commits)" for f, n in area["cochange"]) or "(none)"
    hot = "\n".join(f"- {f} ({n} commits)" for f, n in area["hot"]) or "(none)"
    return (f"# Area {area['name']}: {', '.join(area['paths'])}\n\n## Code map\n{area['map']}\n\n"
            f"## Importers outside the area\n{importers}\n\n## Co-changed files outside the area\n{cochange}\n\n"
            f"## Most-churned files in the area\n{hot}\n\n## Tests\n{area['tests']}\n")


def render_docs(docs: dict) -> str:
    def inline(title: str, files: dict) -> str:
        return f"# {title}\n\n" + ("\n\n".join(f"## {p}\n\n{body}" for p, body in files.items()) or "(none)")

    return "\n\n".join([
        inline("Agent guides on the touched paths", docs["guides"]),
        inline("READMEs on the touched paths", docs["readmes"]),
        inline("OWNERS files on the touched paths", docs["owners"]),
        "# Other docs\n\n" + ("\n".join(f"- {p}" for p in docs["docs"]) or "(none)")
        + (f"\n- … {docs['docsDropped']} more" if docs["docsDropped"] else ""),
        "# Lint and style configs\n\n" + ("\n".join(f"- {p}" for p in docs["styleConfigs"]) or "(none)"),
    ]) + "\n"


def render_history(history: dict, open_hits: list[dict], tickets: dict, reviewers: list) -> str:
    commits = "\n".join(f"- {c['date']} {c['sha'][:10]} {c['author']}: {c['subject']}" for c in history["commits"])
    opened = "\n".join(f"- #{p['number']}{' [draft]' if p['draft'] else ''} {p['title']} (@{p['author']}) "
                       f"touches {', '.join(p['touched'][:10])}" for p in open_hits)
    return (f"# Open PRs touching the same paths\n\n{opened or '(none)'}\n\n"
            f"# Linear tickets (id: where referenced)\n\n"
            + ("\n".join(f"- {t}: {', '.join(w)}" for t, w in tickets.items()) or "(none)")
            + f"\n\n# Most active reviewers here\n\n"
            + ("\n".join(f"- {who} ({n} comments)" for who, n in reviewers) or "(none)")
            + f"\n\n# Owners by commit count\n\n" + ("\n".join(f"- {o}" for o in history["owners"]) or "(none)")
            + f"\n\n# Recent commits (newest first)\n\n{commits or '(none)'}\n")


def digest(ctx: Path, areas: list[dict], docs: dict, prs: list[dict], profiles: dict, open_hits: list[dict],
           tickets: dict, reviewers: list, warnings: list[str]) -> str:
    lines = [f"llp context: {ctx}", ""]
    for area in areas:
        lines.append(f"## area {area['name']} — {len(area['files'])} files → {ctx}/areas/{area['name']}.md")
        if area["importers"]:
            lines.append("  importers: " + ", ".join(p for p, _ in area["importers"][:DIGEST_IMPORTERS])
                         + (f" (+{len(area['importers']) - DIGEST_IMPORTERS})" if len(area["importers"]) > DIGEST_IMPORTERS else ""))
        if area["cochange"]:
            lines.append("  co-changes with: " + ", ".join(f"{f} ({n})" for f, n in area["cochange"][:DIGEST_COCHANGE]))
    lines += [
        "",
        f"docs → {ctx}/docs.md: {len(docs['guides'])} agent guides, {len(docs['readmes'])} READMEs, "
        f"{len(docs['owners'])} OWNERS files, {len(docs['docs'])} other docs",
        f"review history → {ctx}/prs/: {len(prs)} PRs with human review threads "
        f"({sum(len(p['threads']) for p in prs)} threads, {sum(p['state'] == 'OPEN' for p in prs)} open PRs)",
        f"reviewer profiles → {ctx}/profiles/: {', '.join(profiles) or '(none)'}",
        f"reviewers here: {', '.join(f'{who} ({n})' for who, n in reviewers[:5]) or '(none)'}",
        "open PRs on these paths: " + (", ".join(f"#{p['number']}" for p in open_hits) or "(none)"),
        "tickets: " + (", ".join(tickets) or "(none)"),
        f"history, open PRs, tickets → {ctx}/history.md",
    ]
    lines += [f"warning: {w}" for w in warnings]
    return "\n".join(lines)


def build(area_specs: list[str], plan: str) -> None:
    areas = parse_areas(area_specs)
    repo = rp.repo_top()
    head = rp.run("git", "rev-parse", "HEAD").strip()
    warnings: list[str] = []
    anchored = {p: rp.existing_anchor(repo, p) for a in areas for p in a["paths"]}
    # A path with nothing tracked above it would sweep the whole repo; keep it out.
    unanchored = sorted(p for p, anchor in anchored.items() if not anchor)
    if unanchored:
        warnings.append(f"no tracked files at or above {', '.join(unanchored)}: left out of the code map, history, and PR search")
    anchors = sorted({a for a in anchored.values() if a}) or ["."]
    prefixes = sorted({p for p in anchored if p not in unanchored} | set(anchors) - {"."}) or [""]

    key = hashlib.sha1(json.dumps(areas).encode()).hexdigest()[:10]
    common_dir = Path(os.path.abspath(rp.run("git", "rev-parse", "--git-common-dir").strip()))
    ctx = common_dir / "low-level-plan" / f"{head[:12]}-{key}"
    tmp = ctx.with_name(ctx.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    for sub in ("areas", "prs", "profiles"):
        (tmp / sub).mkdir(parents=True)

    # Area threads only submit leaf work to `pool`, so the two pools can't deadlock.
    with ThreadPoolExecutor(max_workers=16) as pool, ThreadPoolExecutor(max_workers=len(areas)) as area_pool:
        docs = pool.submit(rp.gather_docs, repo, anchors)
        history = pool.submit(rp.gather_history, repo, anchors)
        gh = pool.submit(reviews.github_repo)
        open_hits = pool.submit(reviews.open_prs, prefixes)
        contexts = area_pool.map(lambda a: area_context(repo, a, anchored, pool, warnings), areas)

        prs, profiles = [], {}
        if gh.result() is None:
            warnings.append("gh could not resolve a GitHub repo: no PR history, open PRs, or reviewer profiles")
        else:
            owner, name = gh.result()
            numbers = reviews.prs_for_commits(owner, name, history.result()["commits"], pool)
            if len(numbers) > MAX_PRS:
                warnings.append(f"PR history capped at the {MAX_PRS} newest of {len(numbers)} PRs")
            numbers = numbers[:MAX_PRS] + [p["number"] for p in open_hits.result() if p["number"] not in numbers]
            fetched = pool.map(lambda n: reviews.fetch_pr(owner, name, n, prefixes), numbers)
            # Only PRs with human review comments are worth reading; the rest stay as commit history.
            prs = [p for p in fetched if p and (p["threads"] or p["general"])]

        reviewers = Counter(c["author"] for p in prs for t in p["threads"] for c in t["comments"] if c["author"] != p["author"])
        if prs:
            # The plan's author isn't their own reviewer.
            me = reviews.viewer_login()
            top = [who for who, _ in reviewers.most_common() if who != me][:MAX_PROFILED_REVIEWERS]
            mined = {p["number"] for p in prs}
            for login, text in zip(top, pool.map(lambda who: reviews.reviewer_profile(owner, name, who, mined), top)):
                if text:
                    profiles[login] = text
        contexts = list(contexts)

    open_list = open_hits.result() if gh.result() else []
    tickets = reviews.find_tickets(plan, prs)
    for pr in prs:
        (tmp / "prs" / f"{pr['number']}.md").write_text(reviews.render_pr(pr))
    for login, text in profiles.items():
        (tmp / "profiles" / f"{login}.md").write_text(text)
    for area in contexts:
        (tmp / "areas" / f"{area['name']}.md").write_text(render_area(area))
    (tmp / "docs.md").write_text(render_docs(docs.result()))
    (tmp / "history.md").write_text(render_history(history.result(), open_list, tickets, reviewers.most_common(10)))
    if plan:
        (tmp / "plan.md").write_text(plan + "\n")
    # What `llp check` and `llp threads` read back.
    (tmp / "context.json").write_text(json.dumps({
        "repo": str(repo), "head": head, "areas": [{k: a[k] for k in ("name", "paths", "anchors", "files")} for a in contexts],
        "openPrs": open_list, "prs": prs, "reviewers": reviewers.most_common(), "tickets": tickets,
    }))

    shutil.rmtree(ctx, ignore_errors=True)
    tmp.rename(ctx)
    print(digest(ctx, contexts, docs.result(), prs, profiles, open_list, tickets, reviewers.most_common(), warnings))
