"""`llp check`: a mechanical sweep over a low-level plan, in the shape of aster's prepush-pass.

It parses the plan's file sections and skeletons, checks every claim it can verify
against the repo (and the `llp context` dir, when given), and prints BLOCK findings
(fix them) and WORKSHEET items (fix, or resolve with `<id> <justification>`). The
exit code is 0 only when nothing is open, so it can gate presenting the plan.
"""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import repo as rp

ID_TOKEN = r"[A-Z]{1,2}\d{1,3}"
CODE_ID = re.compile(rf"(?:#|//|--|/\*)\s*({ID_TOKEN})\b")
BULLET_ID = re.compile(rf"^\s*[-*]\s+\*\*({ID_TOKEN})\*\*")
ID_REF = re.compile(rf"\b({ID_TOKEN})\b")
FILE_HEADING = re.compile(r"^`?([^\s`]+)`?\s+\[(new|modify|delete)\]\s*$")
DECL = re.compile(r"^\s*(?:@\S+\s+)*(?:pub(?:\([^)]*\))?\s+)?(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:unsafe\s+)?"
                  r"(def|class|fn|struct|enum|trait|interface|type|func|impl)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")
BAZEL_LABEL = re.compile(r"//([\w./-]+):([\w.+-]+)")
PATH_TOKEN = re.compile(r"`?((?:[\w.-]+/)+[\w.-]+\.\w+)`?")
EVIDENCE = re.compile(r"#\d+|@[\w-]+|[\w.-]+/[\w./-]+|\.md\b")
RECOMMENDATION = re.compile(r"recommend|→|->|\bdefault\b|\bsuggest|\bpropose", re.I)
# Names too generic to search the repo for twins.
COMMON_NAMES = {"main", "new", "run", "init", "setup", "default", "from", "into", "build", "create", "get", "set",
                "update", "load", "save", "close", "start", "stop", "parse", "validate", "config", "Config", "Error"}
CONSTRUCTORS = {"__init__", "new", "constructor"}
MAX_LISTED = 8
COCHANGE_MIN_SHARED = 3


@dataclass
class Decl:
    name: str
    kind: str
    plan_line: int
    item_id: str | None
    # The ID of the enclosing item, for members of a new class that carry no ID of their own.
    parent_id: str | None = None
    # The enclosing class or impl, so a changed constructor is checked against the type's callers.
    parent_name: str | None = None


@dataclass
class FileSection:
    path: str
    label: str
    heading_line: int
    has_code: bool = False
    decls: list[Decl] = field(default_factory=list)


@dataclass
class Plan:
    text: str
    sections: dict[str, list[tuple[int, str]]]
    files: list[FileSection]
    id_defs: dict[str, list[int]]
    id_refs: list[tuple[str, int]]


@dataclass
class Finding:
    block: bool
    rule: str
    subject: str
    where: str
    message: str

    @property
    def item_id(self) -> str:
        return f"{self.rule}-{hashlib.md5(f'{self.rule}:{self.subject}'.encode()).hexdigest()[:8]}"


def parse_plan(text: str) -> Plan:
    sections: dict[str, list[tuple[int, str]]] = {}
    files: list[FileSection] = []
    id_defs: dict[str, list[int]] = {}
    id_refs: list[tuple[str, int]] = []
    current_title, current_file, fence = None, None, 0
    enclosing: list[tuple[int, str | None, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        ticks = re.match(r"^\s*(`{3,})", line)
        if fence:
            if ticks and len(ticks.group(1)) >= fence and not line.strip().strip("`"):
                fence = 0
                continue
            comment = CODE_ID.search(line)
            own_id = comment.group(1) if comment else None
            if own_id:
                id_defs.setdefault(own_id, []).append(number)
            decl = DECL.match(line)
            if current_file and decl:
                indent = len(line) - len(line.lstrip())
                enclosing = [entry for entry in enclosing if entry[0] < indent]
                parent = next((item for _, item, _ in reversed(enclosing) if item), None)
                parent_name = enclosing[-1][2] if enclosing else None
                current_file.decls.append(Decl(decl.group(2), decl.group(1), number, own_id, parent, parent_name))
                enclosing.append((indent, own_id or parent, decl.group(2)))
            id_refs += [(ref, number) for ref in ID_REF.findall(line) if ref != own_id]
            continue
        if ticks:
            fence = len(ticks.group(1))
            enclosing = []
            if current_file:
                current_file.has_code = True
            continue
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current_title = heading.group(1)
            sections[current_title] = []
            match = FILE_HEADING.match(current_title)
            current_file = FileSection(match.group(1), match.group(2), number) if match else None
            if current_file:
                files.append(current_file)
            continue
        if current_title is not None:
            sections[current_title].append((number, line))
        bullet = BULLET_ID.match(line)
        if bullet:
            id_defs.setdefault(bullet.group(1), []).append(number)
        id_refs += [(ref, number) for ref in ID_REF.findall(line[bullet.end():] if bullet else line)]
    return Plan(text, sections, files, id_defs, id_refs)


def section(plan: Plan, prefix: str) -> list[tuple[int, str]] | None:
    name = next((t for t in plan.sections if t.lower().startswith(prefix.lower()) and not FILE_HEADING.match(t)), None)
    return plan.sections[name] if name is not None else None


def bullets(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Top-level bullets with their continuation lines joined."""
    out: list[tuple[int, str]] = []
    for number, line in lines:
        if re.match(r"^[-*]\s+", line):
            out.append((number, line))
        elif out and line.startswith(" ") and line.strip():
            out[-1] = (out[-1][0], out[-1][1] + " " + line.strip())
    return [(n, b) for n, b in out if not re.match(r"^[-*]\s+(\.\.\.|…|none\b)", b, re.I)]


def mentioned(plan: Plan, path: str) -> bool:
    return path in plan.text


# ---------------------------------------------------------------- rules


def structure_findings(plan: Plan, repo: Path) -> list[Finding]:
    found = []
    for required in ("Summary", "Tests"):
        if section(plan, required) is None:
            found.append(Finding(True, "S1", required, "plan", f"no `## {required}` section"))
    if not plan.files:
        found.append(Finding(True, "S2", "files", "plan", "no file sections (`## path  [new|modify|delete]`)"))
    for item, lines in plan.id_defs.items():
        if len(lines) > 1:
            found.append(Finding(True, "S4", item, f"plan:{lines[1]}", f"ID {item} is defined {len(lines)} times (lines {', '.join(map(str, lines))})"))
    for f in plan.files:
        where = f"plan:{f.heading_line}"
        if f.label != "delete" and not f.has_code:
            found.append(Finding(True, "S3", f.path, where, f"{f.path} [{f.label}] has no skeleton code block"))
        exists = bool(rp.tracked(repo, f.path))
        if f.label in ("modify", "delete") and not exists:
            found.append(Finding(True, "S5", f.path, where, f"{f.path} is labelled [{f.label}] but isn't tracked at HEAD"))
        if f.label == "new" and exists:
            found.append(Finding(True, "S6", f.path, where, f"{f.path} is labelled [new] but already exists — [modify]?"))
    for number, line in bullets(section(plan, "Open questions") or []):
        if not RECOMMENDATION.search(line):
            found.append(Finding(True, "Q1", line.strip()[:80], f"plan:{number}",
                                 "open question has no recommended answer — add one so silence still leaves a workable plan"))
    return found


def reference_findings(plan: Plan) -> list[Finding]:
    # Only ID-shaped tokens whose prefix the plan actually uses, so H100 or P99 in prose don't count.
    prefixes = {re.match(r"[A-Z]+", item).group(0) for item in plan.id_defs}
    found, seen = [], set()
    for ref, number in plan.id_refs:
        if ref in plan.id_defs or ref in seen or re.match(r"[A-Z]+", ref).group(0) not in prefixes:
            continue
        seen.add(ref)
        found.append(Finding(False, "G2", ref, f"plan:{number}", f"{ref} is referenced but never defined as an item ID"))
    return found


def file_definitions(repo: Path, path: str) -> set[str]:
    try:
        source = (repo / path).read_text(errors="replace")
    except OSError:
        return set()
    return {m.group(2) for m in map(DECL.match, source.splitlines()) if m}


def symbol_findings(plan: Plan, repo: Path, pool: ThreadPoolExecutor) -> list[Finding]:
    found: list[Finding] = []
    plan_paths = {f.path for f in plan.files}

    def check_file(f: FileSection) -> list[Finding]:
        out: list[Finding] = []
        existing = file_definitions(repo, f.path) if f.label == "modify" else set()
        importer_paths: list[str] | None = None
        for decl in f.decls:
            where = f"plan:{decl.plan_line}"
            subject = f"{f.path}:{decl.name}"
            if f.label == "modify" and decl.item_id is None and decl.parent_id is None and decl.name not in existing:
                out.append(Finding(False, "G1", subject, where,
                                   f"anchor `{decl.name}` isn't defined in {f.path} — wrong name, or a new item missing its ID?"))
            elif f.label == "modify" and decl.item_id and decl.name in existing:
                # A changed constructor breaks the type's callers, not callers of `__init__`/`new`.
                searched = decl.parent_name if decl.name in CONSTRUCTORS and decl.parent_name else decl.name
                if searched.startswith("__"):
                    continue
                if importer_paths is None:
                    importer_paths = rp.file_importers(repo, f.path)
                    if Path(f.path).suffix in (".rs", ".go"):
                        importer_paths += rp.tracked(repo, str(Path(f.path).parent))
                candidates = set(importer_paths) - plan_paths - {f.path}
                callers = sorted({p for p, _, _ in rp.symbol_mentions(repo, searched) if p in candidates})
                callers = [p for p in callers if not mentioned(plan, p)]
                if callers:
                    out.append(Finding(False, "T1", subject, where,
                                       f"{decl.item_id} changes existing `{searched if searched != decl.name else decl.name}`"
                                       + (f" (via {decl.name})" if searched != decl.name else "")
                                       + "; callers the plan never mentions: "
                                       + ", ".join(callers[:MAX_LISTED]) + (f" (+{len(callers) - MAX_LISTED})" if len(callers) > MAX_LISTED else "")
                                       + " — update them in the plan, or justify (e.g. signature and contract unchanged)"))
            if decl.item_id and (f.label == "new" or decl.name not in existing) and len(decl.name) > 3 \
                    and decl.name not in COMMON_NAMES and not decl.name.startswith("test"):
                twins = [(p, n) for p, n, _ in rp.definitions(repo, decl.name) if p != f.path]
                if twins:
                    out.append(Finding(False, "R1", subject, where,
                                       f"new `{decl.name}` ({decl.item_id}) — already defined at "
                                       + ", ".join(f"{p}:{n}" for p, n in twins[:5]) + " — reuse it, or say why it doesn't fit"))
        if f.label == "delete":
            users = [p for p in rp.file_importers(repo, f.path) if p not in plan_paths and not mentioned(plan, p)]
            if users:
                out.append(Finding(True, "S7", f.path, f"plan:{f.heading_line}",
                                   f"{f.path} is deleted but still imported by " + ", ".join(users[:MAX_LISTED])))
        if f.label in ("modify", "delete"):
            partners, _ = rp.cochange(repo, [f.path], [f.path])
            missing = [(p, n) for p, n in partners if n >= COCHANGE_MIN_SHARED and p not in plan_paths and not mentioned(plan, p)]
            if missing:
                out.append(Finding(False, "T2", f.path, f"plan:{f.heading_line}",
                                   f"{f.path} historically changes together with "
                                   + ", ".join(f"{p} ({n} commits)" for p, n in missing[:5])
                                   + " — add the wiring to the plan, or justify why this change doesn't need it"))
        if f.label == "new":
            build = rp.owning_build(repo, f.path)
            if build and not mentioned(plan, build):
                out.append(Finding(False, "B1", f.path, f"plan:{f.heading_line}",
                                   f"new {f.path} lands in Bazel package {Path(build).parent}; the plan never mentions {build}"))
        return out

    for result in pool.map(check_file, plan.files):
        found += result
    return found


def tests_findings(plan: Plan, repo: Path) -> list[Finding]:
    found = []
    new_paths = {f.path for f in plan.files if f.label == "new"}
    for number, line in section(plan, "Tests") or []:
        for path in PATH_TOKEN.findall(line):
            if path not in new_paths and not rp.tracked(repo, path) and not re.search(r"\bnew\b", line, re.I):
                found.append(Finding(False, "X1", path, f"plan:{number}",
                                     f"test file {path} doesn't exist and isn't a [new] file section — wrong path, or mark it new"))
    for number, line in enumerate(plan.text.splitlines(), 1):
        for package, target in BAZEL_LABEL.findall(line):
            builds = [f"{package}/{name}" for name in rp.BUILD_NAMES if (repo / package / name).is_file()]
            if any(mentioned(plan, b) for b in builds) or any(f.path.startswith(package + "/BUILD") for f in plan.files):
                continue
            text = "".join((repo / b).read_text(errors="replace") for b in builds)
            if not re.search(rf"\bname\s*=\s*\"{re.escape(target)}\"", text):
                found.append(Finding(False, "X2", f"//{package}:{target}", f"plan:{number}",
                                     f"Bazel target //{package}:{target} doesn't exist and its BUILD file isn't in the plan"))
    return found


def context_findings(plan: Plan, ctx: dict | None) -> list[Finding]:
    if ctx is None:
        return []
    found = []
    touched = {f.path for f in plan.files if f.label in ("modify", "delete")}
    conventions = section(plan, "Conventions")
    for number, line in bullets(conventions or []):
        if not EVIDENCE.search(line):
            found.append(Finding(False, "C1", line.strip()[:80], f"plan:{number}",
                                 "convention without evidence — cite the PR (#123 @reviewer), doc path, or file:line it comes from"))
    threads_by_path: dict[str, list[int]] = {}
    for pr in ctx["prs"]:
        for thread in pr["threads"]:
            threads_by_path.setdefault(thread["path"], []).append(pr["number"])
    if conventions is None and any(t["inArea"] for pr in ctx["prs"] for t in pr["threads"]):
        found.append(Finding(False, "C2", "conventions", "plan",
                             f"{len(ctx['prs'])} past PRs have human review threads on these areas, but the plan has no "
                             "`## Conventions` section"))
    for path in sorted(touched):
        if path in threads_by_path:
            numbers = sorted(set(threads_by_path[path]))
            found.append(Finding(False, "P1", path, "plan",
                                 f"{len(threads_by_path[path])} past review threads on {path} (PRs "
                                 + ", ".join(f"#{n}" for n in numbers[:MAX_LISTED])
                                 + f") — read them (`llp threads {path}`) and carry any rule that applies into Conventions"))
    for pr in ctx["openPrs"]:
        overlap = sorted(touched & set(pr["touched"]))
        if overlap and f"#{pr['number']}" not in plan.text:
            found.append(Finding(False, "O1", str(pr["number"]), "plan",
                                 f"open PR #{pr['number']} ({pr['title']}, @{pr['author']}) also changes "
                                 + ", ".join(overlap) + " — say how the plan sequences with it"))
    return found


# ---------------------------------------------------------------- report


def load_resolutions(path: Path | None) -> dict[str, str]:
    resolutions: dict[str, str] = {}
    if path is None or not path.exists():
        return resolutions
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, justification = line.partition(" ")
        resolutions[head.rstrip(":")] = justification.strip()
    return resolutions


def check(plan_path: Path, resolutions_path: Path | None, ctx_dir: Path | None) -> int:
    repo = rp.repo_top()
    plan = parse_plan(plan_path.read_text())
    ctx = json.loads((ctx_dir / "context.json").read_text()) if ctx_dir else None
    with ThreadPoolExecutor(max_workers=8) as pool:
        findings = (structure_findings(plan, repo) + reference_findings(plan) + symbol_findings(plan, repo, pool)
                    + tests_findings(plan, repo) + context_findings(plan, ctx))
    resolutions = load_resolutions(resolutions_path)
    blocks = [f for f in findings if f.block]
    open_items = [f for f in findings if not f.block and not resolutions.get(f.item_id)]
    resolved = [f for f in findings if not f.block and resolutions.get(f.item_id)]

    if blocks:
        print(f"== BLOCK ({len(blocks)}) — fix these; not justifiable ==")
        for f in sorted(blocks, key=lambda f: (f.rule, f.where)):
            print(f"  {f.rule}  {f.where}  {f.message}")
    if open_items:
        print(f"\n== WORKSHEET ({len(open_items)} open) — fix the plan, or add `<id> <justification>` to the resolutions file ==")
        for f in sorted(open_items, key=lambda f: (f.rule, f.where)):
            print(f"  [{f.item_id}]\n      {f.where}  {f.message}")
    if resolved:
        decided = [f for f in resolved if resolutions[f.item_id].lower().startswith("user:")]
        justified = [f for f in resolved if f not in decided]
        if decided:
            print(f"\n== decided by the user ({len(decided)}) — record these in the plan's Decisions ==")
            for f in decided:
                print(f"  [{f.item_id}] {resolutions[f.item_id]}")
        if justified:
            print(f"\n== resolved ({len(justified)}) — carry these into Deviations or Open questions ==")
            for f in justified:
                print(f"  [{f.item_id}] {resolutions[f.item_id]}")
    if ctx_dir is None:
        print("\nnote: no --ctx given, so conventions, past-review (P1), and open-PR (O1) checks were skipped")
    if not blocks and not open_items:
        print("llp check: clean")
        return 0
    print(f"\nllp check: {len(blocks)} block(s), {len(open_items)} open worksheet item(s)")
    return 1
