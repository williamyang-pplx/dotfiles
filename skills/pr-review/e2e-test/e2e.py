#!/usr/bin/env python3
"""Bookkeeping for the e2e-test skill: research context, stacked branch, infra preflight, run gate, report.

Usage: e2e.py <command> [args]   (run from a checkout of the PR's repo)

  context [<pr>]                   gather the PR's claims, diff, and research signals
  branch --slug <s> [--worktree]   create the stacked e2e branch off the PR branch
  push                             push the e2e branch plainly; refuses if it has a PR
  restack                          rebase the e2e branch onto the rewritten PR branch
  preflight <target> [-p k=v ...]  check credentials and reachability for a target recipe
  run -- <cmd ...>                 run the test, parse E2E PASS/FAIL lines, enforce coverage
  report [--result <text>]         print Testing Strategy bullets from fresh green runs

State lives in <git-common-dir>/e2e-test/<pr-branch>/ so every worktree shares
it, and is found from the current branch (the PR branch or its e2e branch).
Exits non-zero with a list of what to fix whenever a gate is not met.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
CHECK_LINE = re.compile(r"\bE2E (PASS|FAIL) (\S+)(?: covers=([\w,-]+))?")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TICKET_KEY = re.compile(r"[a-z]+-\d+", re.IGNORECASE)
ENV_REF = re.compile(
    r"""(?:environ(?:\.get)?\s*[\[(]|getenv\s*\(|env::var\s*\(|process\.env\.|ENV\[)\s*["']?([A-Z][A-Z0-9_]{2,})"""
)
PUBLIC_DEF = re.compile(
    r"^\+\s*(?:(?:async\s+)?def|class|(?:pub(?:\([\w:]+\))?\s+)?fn|export\s+(?:async\s+)?(?:function|class|const)|func(?:\s+\([^)]*\))?)\s+([A-Za-z]\w*)"
)
CLI_HOOK = re.compile(r"^\+.*(@\w+\.command|add_parser\(|add_typer\(|\[project\.scripts\]|clap::|#\[command)")
TEST_FILE = re.compile(r"(?:^|/)(?:test_[^/]+\.py|[^/]+_test\.(?:py|go|rs)|[^/]+\.(?:test|spec)\.[jt]sx?)$")
MAX_TEST_HINTS = 40
MAX_PRIOR_BRANCHES = 10


def run(*cmd: str, check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit(f"e2e: `{' '.join(cmd[:4])} ...` failed:\n{result.stderr.strip()}")
    return result.stdout.strip() if result.returncode == 0 else ""


def fail(problems: list[str], hint: str = "") -> None:
    sys.exit("e2e: NOT READY\n" + "\n".join(f"  - {p}" for p in problems) + (f"\n{hint}" if hint else ""))


def is_ancestor(older: str, newer: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], capture_output=True).returncode == 0


def current_branch() -> str:
    return run("git", "branch", "--show-current")


def ctx_root() -> Path:
    return Path(os.path.abspath(run("git", "rev-parse", "--git-common-dir"))) / "e2e-test"


def save_state(ctx: Path, state: dict) -> None:
    (ctx / "state.json").write_text(json.dumps(state, indent=2) + "\n")


def find_state() -> tuple[Path, dict]:
    branch = current_branch()
    for state_file in sorted(ctx_root().glob("*/state.json")):
        state = json.loads(state_file.read_text())
        if branch in (state["prBranch"], state.get("e2eBranch")):
            return state_file.parent, state
    sys.exit(f"e2e: no e2e context for branch `{branch}`. Run `e2e.py context` from the PR branch first.")


def require_e2e_checkout(state: dict) -> str:
    name = state.get("e2eBranch")
    if not name:
        sys.exit("e2e: no e2e branch yet. Run `e2e.py branch --slug <slug>` first.")
    if current_branch() != name:
        where = f" (worktree: {state['worktree']})" if state.get("worktree") else ""
        sys.exit(f"e2e: run this from the e2e branch `{name}`{where}.")
    return name


def fetch_remote_head(branch: str) -> str | None:
    if subprocess.run(["git", "fetch", "-q", "origin", branch], capture_output=True).returncode != 0:
        return None
    return run("git", "rev-parse", f"origin/{branch}")


def compare_url(state: dict) -> str:
    return f"https://github.com/{state['owner']}/{state['repo']}/compare/{state['prBranch']}...{state['e2eBranch']}?expand=1"


# --- context ------------------------------------------------------------------


def check_pr_branch_current(pr_branch: str, remote_head: str) -> None:
    local = run("git", "rev-parse", "--verify", "-q", f"refs/heads/{pr_branch}", check=False)
    if not local or local == remote_head:
        return
    if is_ancestor(local, remote_head):
        fail([f"local `{pr_branch}` is behind origin."], f"Run `git pull --ff-only` on `{pr_branch}`, then rerun.")
    if is_ancestor(remote_head, local):
        fail([f"local `{pr_branch}` has unpushed commits."], "Push them with /push-stacked-pr first, then rerun.")
    fail([f"local `{pr_branch}` and origin have diverged."], "Reconcile them with the user before testing.")


def research_signals(diff: str, changed: list[str], tree: list[str], pr_branch: str) -> str:
    env_vars, defs, cli_hooks, path = set(), {}, set(), None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        env_vars.update(ENV_REF.findall(line))
        public_def = PUBLIC_DEF.match(line)
        if public_def:
            defs.setdefault(path, []).append(public_def.group(1))
        if CLI_HOOK.match(line):
            cli_hooks.add(path)

    changed_dirs = {str(Path(p).parent) for p in changed}
    test_dirs = changed_dirs | {f"{d}/tests" for d in changed_dirs} | {f"{Path(d).parent}/tests" for d in changed_dirs}
    tests = [p for p in tree if TEST_FILE.search(p) and str(Path(p).parent) in test_dirs]
    prior_art = [p for p in tree if re.search(r"(?:^|/)[^/]*(?:e2e|manual|smoke)[^/]*$", p, re.IGNORECASE)]
    prior_branches = run("git", "branch", "-r", "--sort=-committerdate", "--list", "origin/*e2e-manual*").splitlines()

    def bullets(items, empty="(none found)"):
        return "\n".join(f"- {item}" for item in items) or empty

    sections = [
        ("Env vars the diff reads (credentials and config the test must supply)", bullets(sorted(env_vars))),
        ("Public entry points the diff adds or changes", bullets(f"{p}: {', '.join(names)}" for p, names in defs.items())),
        ("Files that wire a CLI command", bullets(sorted(cli_hooks))),
        (f"Existing tests next to the changed files (first {MAX_TEST_HINTS})", bullets(tests[:MAX_TEST_HINTS])),
        ("Existing e2e/manual/smoke scripts in the repo", bullets(prior_art[:MAX_TEST_HINTS])),
        (
            "Earlier `-e2e-manual` branches (prior art for test shape)",
            bullets(b.strip() for b in prior_branches[:MAX_PRIOR_BRANCHES] if pr_branch not in b),
        ),
    ]
    return "\n\n".join(f"## {title}\n\n{body}" for title, body in sections) + "\n"


def cmd_context(args: argparse.Namespace) -> None:
    meta = json.loads(run(
        "gh", "pr", "view", *([args.pr] if args.pr else []), "--json",
        "number,title,body,url,headRefName,headRefOid,baseRefName,commits",
    ))
    owner_repo = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/\d+", meta["url"])
    if not owner_repo:
        sys.exit(f"e2e: can't parse owner/repo from {meta['url']}")
    pr_branch, base_branch = meta["headRefName"], meta["baseRefName"]

    remote_head = fetch_remote_head(pr_branch)
    if remote_head is None or fetch_remote_head(base_branch) is None:
        sys.exit(f"e2e: can't fetch `{pr_branch}` and `{base_branch}` from origin. Run this from the PR's repo.")
    if remote_head != meta["headRefOid"]:
        sys.exit(f"e2e: origin/{pr_branch} is {remote_head[:12]} but GitHub's PR head is {meta['headRefOid'][:12]}; rerun.")
    check_pr_branch_current(pr_branch, remote_head)

    merge_base = run("git", "merge-base", f"origin/{base_branch}", remote_head)
    diff = run("git", "diff", "-M", merge_base, remote_head)
    changed = run("git", "diff", "--name-only", "-M", merge_base, remote_head).splitlines()
    tree = run("git", "ls-tree", "-r", "--name-only", remote_head).splitlines()

    ctx = ctx_root() / pr_branch.replace("/", "__")
    (ctx / "runs").mkdir(parents=True, exist_ok=True)
    commits = "\n".join(f"- {c['messageHeadline']}" for c in meta["commits"])
    (ctx / "pr.md").write_text(f"# {meta['title']}\n\n{meta['url']}\n\n{meta['body'] or '(no description)'}\n\n## Commits\n\n{commits}\n")
    (ctx / "diff.patch").write_text(diff + "\n")
    (ctx / "signals.md").write_text(research_signals(diff, changed, tree, pr_branch))

    state_file = ctx / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {"targets": {}}
    state.update(
        number=meta["number"], url=meta["url"], owner=owner_repo.group(1), repo=owner_repo.group(2),
        prBranch=pr_branch, baseBranch=base_branch, prHead=remote_head,
    )
    save_state(ctx, state)
    print(f"context: {ctx}\n  pr.md        claims to disprove (PR title, body, commits)")
    print(f"  diff.patch   {len(changed)} files vs {base_branch}\n  signals.md   env vars, entry points, nearby tests, prior e2e art")
    if state.get("e2eBranch"):
        print(f"  e2e branch   {state['e2eBranch']} (already created)")


# --- branch / push / restack --------------------------------------------------


def e2e_branch_name(pr_branch: str, slug: str) -> str:
    prefix, _, leaf = pr_branch.rpartition("/")
    ticket = TICKET_KEY.match(leaf)
    leaf_parts = ([ticket.group(0).lower()] if ticket else []) + [slug, "e2e-manual"]
    return "/".join(filter(None, [prefix, "-".join(leaf_parts)]))


def cmd_branch(args: argparse.Namespace) -> None:
    ctx, state = find_state()
    slug = args.slug.removesuffix("-e2e-manual")
    if not SLUG.fullmatch(slug):
        sys.exit(f"e2e: slug `{slug}` must be lowercase kebab-case, e.g. `e2b`.")
    name = e2e_branch_name(state["prBranch"], slug)
    pr_head = fetch_remote_head(state["prBranch"]) or sys.exit(f"e2e: can't fetch origin/{state['prBranch']}.")

    if run("git", "rev-parse", "--verify", "-q", f"refs/heads/{name}", check=False):
        if not is_ancestor(state.get("branchBase") or pr_head, name):
            sys.exit(f"e2e: `{name}` exists but is not stacked on the PR branch. Inspect it before reusing the name.")
        print(f"e2e branch `{name}` already exists; reusing it.")
    elif args.worktree:
        toplevel = Path(run("git", "rev-parse", "--show-toplevel"))
        worktree = toplevel.parent / f"{toplevel.name}-{slug}-e2e"
        run("git", "worktree", "add", "-q", "-b", name, str(worktree), pr_head)
        state.update(worktree=str(worktree), branchBase=pr_head)
        print(f"created `{name}` in worktree {worktree}")
    else:
        run("git", "checkout", "-q", "-b", name, pr_head)
        state["branchBase"] = pr_head
        print(f"created and checked out `{name}`")

    state["e2eBranch"] = name
    save_state(ctx, state)
    print(f"parent: {state['prBranch']} @ {state['branchBase'][:12]}. Never open a PR for this branch.")


def cmd_push(args: argparse.Namespace) -> None:
    ctx, state = find_state()
    name = require_e2e_checkout(state)
    if run("git", "status", "--porcelain"):
        sys.exit("e2e: commit the e2e changes before pushing.")
    existing_prs = json.loads(run("gh", "pr", "list", "--head", name, "--state", "all", "--json", "number,url,state"))
    if existing_prs:
        found = ", ".join(f"{pr['url']} ({pr['state']})" for pr in existing_prs)
        sys.exit(f"e2e: `{name}` has a PR: {found}. e2e branches never get one. Stop and tell the user.")

    pr_head = fetch_remote_head(state["prBranch"]) or sys.exit(f"e2e: can't fetch origin/{state['prBranch']}.")
    if not is_ancestor(pr_head, "HEAD"):
        sys.exit(f"e2e: origin/{state['prBranch']} moved past this branch. Run `e2e.py restack` first.")

    remote_head = fetch_remote_head(name)
    push = ["git", "push", "-q", "-u", "origin", name]
    if remote_head and not is_ancestor(remote_head, "HEAD"):
        push.insert(2, f"--force-with-lease={name}:{remote_head}")
    run(*push)
    print(f"pushed `{name}` @ {run('git', 'rev-parse', '--short', 'HEAD')}\ncompare: {compare_url(state)}")


def cmd_restack(args: argparse.Namespace) -> None:
    ctx, state = find_state()
    require_e2e_checkout(state)
    rebase_dirs = (run("git", "rev-parse", "--git-path", d) for d in ("rebase-merge", "rebase-apply"))
    if any(Path(d).exists() for d in rebase_dirs):
        sys.exit("e2e: a rebase is in progress. Resolve it (`git rebase --continue`), then rerun restack.")
    if run("git", "status", "--porcelain"):
        sys.exit("e2e: commit or discard local changes before restacking.")

    pr_head = fetch_remote_head(state["prBranch"]) or sys.exit(f"e2e: can't fetch origin/{state['prBranch']}.")
    if not is_ancestor(pr_head, "HEAD"):
        rebase = subprocess.run(["git", "rebase", "-q", "--onto", pr_head, state["branchBase"]], capture_output=True, text=True)
        if rebase.returncode != 0:
            sys.exit(
                f"e2e: rebase hit conflicts:\n{rebase.stderr.strip()}\n"
                "Resolve them mechanically and `git rebase --continue`, then rerun restack. "
                "If a conflict needs a real redesign of the test, stop and ask the user."
            )
    state["branchBase"] = pr_head
    save_state(ctx, state)
    print(f"`{state['e2eBranch']}` sits on {state['prBranch']} @ {pr_head[:12]}. Run `e2e.py push` next.")


# --- preflight ----------------------------------------------------------------


def load_recipe(target: str) -> dict:
    path = SKILL_DIR / "targets" / f"{target}.json"
    path = path if path.exists() else Path(target)
    if not path.exists():
        known = ", ".join(p.stem for p in sorted((SKILL_DIR / "targets").glob("*.json")))
        sys.exit(f"e2e: no target recipe `{target}`. Known: {known}. Or pass a path to a recipe JSON file.")
    return json.loads(path.read_text())


def cmd_preflight(args: argparse.Namespace) -> None:
    ctx, state = find_state()
    recipe = load_recipe(args.target)
    params = dict(kv.split("=", 1) for kv in args.param)
    missing_params = [p for p in recipe.get("params", []) if p not in params]
    if missing_params:
        sys.exit(f"e2e: target `{args.target}` needs " + " ".join(f"-p {p}=<value>" for p in missing_params))

    def fill(template: str) -> str:
        return template.format(**params)

    problems = []
    for var, hint in recipe.get("env", {}).items():
        ok = bool(os.environ.get(var))
        print(f"  {'ok  ' if ok else 'FAIL'} env {var} is set")
        if not ok:
            problems.append(f"env {var} is not set. Fix: {fill(hint)}")
    for probe in recipe.get("probes", []):
        cmd = fill(probe["cmd"])
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=probe.get("timeout", 30))
            detail = f"exited {result.returncode}: {(result.stderr.strip().splitlines() or [''])[-1][:200]}"
            ok = result.returncode == 0
        except subprocess.TimeoutExpired:
            detail, ok = f"timed out after {probe.get('timeout', 30)}s", False
        print(f"  {'ok  ' if ok else 'FAIL'} {probe['name']}")
        if not ok:
            problems.append(f"{probe['name']}: `{cmd}` {detail}. Fix: {fill(probe['fix'])}")
    if problems:
        fail(problems, "Stop and ask the user to fix these; they can run commands here with `! <command>`.")

    target_key = ":".join([Path(args.target).stem, *params.values()])
    state.setdefault("targets", {})[target_key] = {"description": fill(recipe["description"])}
    state["currentTarget"] = target_key
    save_state(ctx, state)
    print(f"preflight: `{target_key}` ready ({fill(recipe['description'])}). Later runs are recorded against it.")


# --- run / report -------------------------------------------------------------


def load_bugs(ctx: Path) -> list[dict]:
    bugs_file = ctx / "bugs.json"
    if not bugs_file.exists():
        sys.exit(f"e2e: write adversarial pass 1's list to {bugs_file} first.")
    bugs = json.loads(bugs_file.read_text())
    ids = [bug.get("id") for bug in bugs]
    if not all(ids) or len(set(ids)) != len(ids) or not all(bug.get("bug") and bug.get("trigger") for bug in bugs):
        sys.exit(f"e2e: {bugs_file} needs a unique `id` and non-empty `bug` and `trigger` on every entry.")
    return bugs


def load_resolutions(ctx: Path) -> dict[str, str]:
    resolutions_file = ctx / "resolutions.txt"
    if not resolutions_file.exists():
        return {}
    pairs = (line.strip().split(maxsplit=1) for line in resolutions_file.read_text().splitlines() if line.strip())
    return {pair[0]: pair[1] for pair in pairs if len(pair) == 2}


def cmd_run(args: argparse.Namespace) -> None:
    ctx, state = find_state()
    require_e2e_checkout(state)
    target_key = state.get("currentTarget") or sys.exit("e2e: run `e2e.py preflight <target>` first.")
    bugs = load_bugs(ctx)
    resolutions = load_resolutions(ctx)
    test_cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not test_cmd:
        sys.exit("e2e: pass the test command after `--`.")
    dirty = bool(run("git", "status", "--porcelain"))

    run_index = len(list((ctx / "runs").glob("*.json"))) + 1
    log_path = ctx / "runs" / f"{run_index:03d}.log"
    statuses, covers = {}, {}
    with log_path.open("w") as log:
        proc = subprocess.Popen(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            sys.stdout.write(line)
            log.write(line)
            check = CHECK_LINE.search(line)
            if check:
                status, name, covered_ids = check.groups()
                statuses[name] = "FAIL" if statuses.get(name) == "FAIL" else status
                covers.setdefault(name, set()).update(filter(None, (covered_ids or "").split(",")))
        exit_code = proc.wait()

    bug_ids = {bug["id"] for bug in bugs}
    covered = {bug_id for name, ids in covers.items() if statuses[name] == "PASS" for bug_id in ids}
    unknown = sorted({bug_id for ids in covers.values() for bug_id in ids} - bug_ids)
    problems = [f"check `{name}` FAILED" for name, status in statuses.items() if status == "FAIL"]
    problems += [f"{bug['id']} ({bug['bug']}) has no passing check and no resolution" for bug in bugs if bug["id"] not in covered | set(resolutions)]
    problems += [f"checks cover unknown ids {', '.join(unknown)} (typo, or missing from bugs.json)"] if unknown else []
    problems += ["no `E2E PASS|FAIL <check>` lines in the output"] if not statuses else []
    problems += [f"test command exited {exit_code}"] if exit_code != 0 else []
    problems += ["working tree is dirty; commit first so the run is tied to a pushed commit"] if dirty else []

    record = {
        "index": run_index, "target": target_key, "e2eHead": run("git", "rev-parse", "HEAD"),
        "at": datetime.datetime.now().isoformat(timespec="seconds"), "command": test_cmd, "exitCode": exit_code,
        "checks": {name: {"status": statuses[name], "covers": sorted(covers[name])} for name in statuses},
        "resolved": {bug_id: why for bug_id, why in resolutions.items() if bug_id in bug_ids - covered},
        "green": not problems, "log": str(log_path),
    }
    (ctx / "runs" / f"{run_index:03d}.json").write_text(json.dumps(record, indent=2) + "\n")

    print(f"\nrun {run_index:03d} against `{target_key}` ({len(statuses)} checks) - log: {log_path}")
    for bug in bugs:
        passing = [name for name, ids in covers.items() if bug["id"] in ids and statuses[name] == "PASS"]
        verdict = f"checked by {', '.join(passing)}" if passing else f"resolved: {resolutions[bug['id']]}" if bug["id"] in resolutions else "MISSING"
        print(f"  {bug['id']:<5} {verdict}")
    if problems:
        fail(problems)
    print("e2e: GREEN. Push with `e2e.py push`, then `e2e.py report`.")


def cmd_report(args: argparse.Namespace) -> None:
    ctx, state = find_state()
    name = state.get("e2eBranch") or sys.exit("e2e: no e2e branch yet.")
    pr_head = fetch_remote_head(state["prBranch"]) or sys.exit(f"e2e: can't fetch origin/{state['prBranch']}.")
    pushed_head = fetch_remote_head(name) or sys.exit(f"e2e: `{name}` is not on origin. Run `e2e.py push`.")

    latest_by_target = {}
    for record_file in sorted((ctx / "runs").glob("*.json")):
        record = json.loads(record_file.read_text())
        latest_by_target[record["target"]] = record
    if not latest_by_target:
        sys.exit("e2e: no recorded runs. Run `e2e.py run -- <cmd>` first.")

    problems, bullets, resolved = [], [], {}
    for target_key, record in latest_by_target.items():
        label = f"run {record['index']:03d} on `{target_key}`"
        if not record["green"]:
            problems.append(f"{label} is not green")
        elif record["e2eHead"] != pushed_head:
            problems.append(f"{label} tested {record['e2eHead'][:12]} but origin/{name} is {pushed_head[:12]}; push or re-run")
        elif not is_ancestor(pr_head, record["e2eHead"]):
            problems.append(f"{label} predates origin/{state['prBranch']} @ {pr_head[:12]}; restack, push, and re-run")
        else:
            checks = len(record["checks"])
            resolved_count = len(record["resolved"])
            result = args.result or f"all {checks} checks passed" + (
                f", {resolved_count} potential bug{'s' if resolved_count != 1 else ''} resolved without a check" if resolved_count else ""
            )
            description = state["targets"][target_key]["description"]
            bullets.append(f"- Ran the manual e2e script (stacked branch [{name}]({compare_url(state)})) against {description} — {result}")
            resolved.update(record["resolved"])
    if problems:
        fail(problems, "Do not update the PR description until every target's latest run is green and current.")

    print("\n".join(bullets))
    if resolved:
        print("\nResolved without a check (put these in the final report):")
        print("\n".join(f"  {bug_id} {why}" for bug_id, why in resolved.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("context").add_argument("pr", nargs="?")
    branch = commands.add_parser("branch")
    branch.add_argument("--slug", required=True)
    branch.add_argument("--worktree", action="store_true")
    commands.add_parser("push")
    commands.add_parser("restack")
    preflight = commands.add_parser("preflight")
    preflight.add_argument("target")
    preflight.add_argument("-p", "--param", action="append", default=[], metavar="KEY=VALUE")
    commands.add_parser("run").add_argument("cmd", nargs=argparse.REMAINDER)
    commands.add_parser("report").add_argument("--result")
    args = parser.parse_args()
    {
        "context": cmd_context, "branch": cmd_branch, "push": cmd_push, "restack": cmd_restack,
        "preflight": cmd_preflight, "run": cmd_run, "report": cmd_report,
    }[args.command](args)


if __name__ == "__main__":
    main()
