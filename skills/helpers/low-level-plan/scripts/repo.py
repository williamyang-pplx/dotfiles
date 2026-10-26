"""Local-repo facts for low-level-plan: code maps, importers, co-change, tests, docs, and history.

Everything here is plain git plus file reads, so it runs in seconds and needs no network.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MAX_AREA_FILES = 400
MAX_OUTLINE_FILE_BYTES = 300_000
COCHANGE_COMMITS = 300
# Commits touching more files than this are mass refactors, not coupling signal.
COCHANGE_MAX_FILES = 40
MAX_COMMITS = 200
MAX_GUIDE_CHARS = 8000
MAX_README_CHARS = 4000
MAX_OWNERS_CHARS = 3000
MAX_LISTED_DOCS = 40

GUIDE_NAMES = ("AGENTS.md", "CLAUDE.md")
README_NAMES = ("README.md", "README")
DOC_NAMES = ("CONTRIBUTING.md", "STYLE.md", "STYLEGUIDE.md", "ARCHITECTURE.md", "DESIGN.md")
OWNER_NAMES = ("OWNERS", "OWNERS.toml", "OWNERS.yaml", "CODEOWNERS", ".github/CODEOWNERS")
BUILD_NAMES = ("BUILD.bazel", "BUILD")
STYLE_CONFIGS = (
    "pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg", ".flake8", "mypy.ini", ".pylintrc",
    ".editorconfig", ".eslintrc", ".eslintrc.js", ".eslintrc.json", "eslint.config.js", "eslint.config.mjs",
    ".prettierrc", "tsconfig.json", "biome.json", ".golangci.yml", ".golangci.yaml", "rustfmt.toml",
    "clippy.toml", ".clang-format", ".clang-tidy", ".pre-commit-config.yaml",
)

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|testing)/|(^|/)test_[^/]+\.py$|_test\.(py|rs|go|ts|js)$"
                       r"|\.(test|spec)\.[jt]sx?$|(^|/)conftest\.py$")
BAZEL_TEST_RULE = re.compile(r"\b(\w*_test|\w*_test_suite)\(\s*name\s*=\s*\"([^\"]+)\"")
RUST_RULE = re.compile(r"\brust_(?:library|proc_macro|binary)\w*\(")
SYMBOL_LINE = {
    ".rs": re.compile(r"^\s*(pub(\([^)]*\))?\s+)?(async\s+)?(unsafe\s+)?(fn|struct|enum|trait|impl|type|mod|macro_rules!)\b"),
    ".ts": re.compile(r"^\s*(export\s+)?(default\s+)?(declare\s+)?(async\s+)?(abstract\s+)?(function|class|interface|type|enum)\b"),
    ".go": re.compile(r"^(func|type)\b"),
    ".proto": re.compile(r"^\s*(message|service|rpc|enum)\b"),
    ".bzl": re.compile(r"^def\s"),
    # Fallback when ast can't parse (newer syntax than the running Python).
    ".py": re.compile(r"^\s*(@|(async\s+)?def\s|class\s)"),
}
for _alias in (".tsx", ".js", ".jsx", ".mjs"):
    SYMBOL_LINE[_alias] = SYMBOL_LINE[".ts"]


def run(*cmd: str, check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if check:
            sys.exit(f"llp: `{' '.join(cmd[:4])} ...` failed:\n{result.stderr.strip()}")
        return ""
    return result.stdout


def git(repo: Path, *args: str) -> str:
    return run("git", "-C", str(repo), *args, check=False)


def repo_top() -> Path:
    return Path(run("git", "rev-parse", "--show-toplevel").strip())


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n… [{len(text) - limit} more chars cut]"


def tracked(repo: Path, *paths: str) -> list[str]:
    return git(repo, "ls-files", "--", *paths).split()


def existing_anchor(repo: Path, rel: str) -> str:
    """Nearest tracked path at or above rel — new files are planned under dirs that already exist.

    Tracked, not merely on disk: stale untracked dirs would anchor history and docs on nothing.
    """
    path = Path(rel)
    while str(path) not in ("", ".") and not tracked(repo, str(path)):
        path = path.parent
    return "" if str(path) == "." else str(path)


def in_area(path: str, prefixes: list[str]) -> bool:
    return any(not p or path == p or path.startswith(p + "/") for p in prefixes)


# ---------------------------------------------------------------- outlines


def outline_python(source: str) -> list[str]:
    def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        decorators = "".join(f"@{ast.unparse(d)} " for d in node.decorator_list)
        return f"{decorators}{prefix} {node.name}({ast.unparse(node.args)}){returns}"

    lines = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(f"{node.lineno}: {signature(node)}")
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases + node.keywords)
            lines.append(f"{node.lineno}: class {node.name}({bases})")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines.append(f"{item.lineno}:     {signature(item)}")
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    lines.append(f"{item.lineno}:     {item.target.id}: {ast.unparse(item.annotation)}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name) and t.id.isupper()]
            if names:
                lines.append(f"{node.lineno}: {', '.join(names)} = …")
    return lines


def outline_file(repo: Path, rel: str) -> tuple[int, list[str]]:
    """(line count, symbol lines) for one file; symbols only for languages we know."""
    path = repo / rel
    try:
        if path.stat().st_size > MAX_OUTLINE_FILE_BYTES:
            return 0, ["(too large to outline)"]
        source = path.read_text(errors="replace")
    except OSError:
        return 0, []
    count = source.count("\n") + 1
    if path.suffix == ".py":
        try:
            return count, outline_python(source)
        except (SyntaxError, ValueError):
            pass
    pattern = SYMBOL_LINE.get(path.suffix)
    if not pattern:
        return count, []
    return count, [f"{i}: {line.strip()[:160]}" for i, line in enumerate(source.splitlines(), 1) if pattern.match(line)]


def code_map(repo: Path, paths: list[str], pool: ThreadPoolExecutor, warnings: list[str]) -> tuple[list[str], str]:
    """(tracked files, rendered map: each file with line count and symbols at file:line)."""
    files = tracked(repo, *paths)
    if len(files) > MAX_AREA_FILES:
        warnings.append(f"code map: kept {MAX_AREA_FILES} of {len(files)} files under {', '.join(paths)}")
        files = files[:MAX_AREA_FILES]
    blocks = [f"### {f} ({count} lines)" + "".join(f"\n  {s}" for s in symbols)
              for f, (count, symbols) in zip(files, pool.map(lambda f: outline_file(repo, f), files))]
    return files, "\n".join(blocks)


# ---------------------------------------------------------------- callers and coupling


def rust_crates(build_text: str) -> list[str]:
    crates = []
    for match in RUST_RULE.finditer(build_text):
        block = build_text[match.end():match.end() + 1500]
        named = re.search(r"\bcrate_name\s*=\s*\"([^\"]+)\"", block) or re.search(r"\bname\s*=\s*\"([^\"]+)\"", block)
        if named:
            crates.append(named.group(1).replace("-", "_"))
    return crates


def owning_build(repo: Path, rel: str) -> str | None:
    """The nearest BUILD file at or above rel's directory."""
    for directory in [Path(rel).parent, *Path(rel).parent.parents]:
        for name in BUILD_NAMES:
            if (repo / directory / name).is_file():
                return str(directory / name)
    return None


def import_patterns(repo: Path, files: list[str], labels: list[str]) -> list[tuple[str, str, re.Pattern]]:
    """(label, fixed-string prefilter for git grep, precise regex) for code that imports these files.

    git grep gets plain strings (macOS git's ERE has no \\b or \\s); Python does the exact match.
    """
    patterns = []
    for f in files:
        p = Path(f)
        if p.suffix == ".py":
            parts = list(p.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            if len(parts) < 2:
                continue
            module, parent, stem = ".".join(parts[-3:]), ".".join(parts[-3:-1]), parts[-1]
            patterns.append((f, module, re.compile(rf"^\s*(from|import)\s+([\w.]*\.)?{re.escape(module)}\b")))
            patterns.append((f, parent, re.compile(rf"^\s*from\s+([\w.]*\.)?{re.escape(parent)}\s+import\s.*\b{re.escape(stem)}\b")))
        elif p.suffix in (".ts", ".tsx", ".js", ".jsx") and p.stem != "index":
            patterns.append((f, f"/{p.stem}", re.compile(rf"from\s+['\"][^'\"]*/{re.escape(p.stem)}['\"]")))
        elif p.name in BUILD_NAMES:
            for crate in rust_crates((repo / f).read_text(errors="replace")):
                patterns.append((f"crate {crate}", f"{crate}::", re.compile(rf"\b{crate}::")))
    patterns += [(f"//{a}", f'"//{a}', re.compile(rf"\"//{re.escape(a)}[:/\"]")) for a in labels]
    return patterns


def importers(repo: Path, files: list[str], labels: list[str], prefixes: list[str]) -> list[tuple[str, list[str]]]:
    """Files outside prefixes that import these files, each with what it pulls in; most-coupled first."""
    patterns = import_patterns(repo, files, labels)
    if not patterns:
        return []
    fixed = list(dict.fromkeys(fx for _, fx, _ in patterns))
    out = git(repo, "grep", "-n", "-I", "-F", *[x for fx in fixed for x in ("-e", fx)])
    hits: dict[str, set[str]] = {}
    for line in out.splitlines():
        path, _, rest = line.partition(":")
        text = rest.partition(":")[2]
        if in_area(path, prefixes):
            continue
        for label, _, rx in patterns:
            if rx.search(text):
                hits.setdefault(path, set()).add(label)
    return sorted(((p, sorted(ls)) for p, ls in hits.items()), key=lambda kv: (-len(kv[1]), kv[0]))


def file_importers(repo: Path, rel: str) -> list[str]:
    """Files that import one file — through its Python/TS module or, for Rust, its crate."""
    files = [rel]
    if Path(rel).suffix == ".rs":
        build = owning_build(repo, rel)
        files += [build] if build else []
    return [path for path, _ in importers(repo, files, [], [rel])]


def symbol_mentions(repo: Path, name: str) -> list[tuple[str, int, str]]:
    """(path, line, text) for whole-word mentions of name across tracked files."""
    out = git(repo, "grep", "-n", "-I", "-w", "-F", "-e", name)
    rows = []
    for line in out.splitlines():
        path, _, rest = line.partition(":")
        number, _, text = rest.partition(":")
        if number.isdigit():
            rows.append((path, int(number), text))
    return rows


def definitions(repo: Path, name: str) -> list[tuple[str, int, str]]:
    """Where name is defined as a function, class, or type, in any language we outline."""
    rx = re.compile(rf"^\s*(pub(\([^)]*\))?\s+)?(export\s+)?(async\s+)?(def|class|fn|struct|enum|trait|interface|type|func)\s+{re.escape(name)}\b")
    return [row for row in symbol_mentions(repo, name) if rx.match(row[2])]


def cochange(repo: Path, paths: list[str], prefixes: list[str]) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """(files outside prefixes that change in the same commits, the most-churned files inside)."""
    out = git(repo, "log", f"-n{COCHANGE_COMMITS}", "--no-merges", "--format=%x00", "--name-only", "--full-diff",
              "HEAD", "--", *paths)
    outside, churn = Counter(), Counter()
    for commit in out.split("\0"):
        touched = commit.split()
        if len(touched) > COCHANGE_MAX_FILES:
            continue
        for f in touched:
            (churn if in_area(f, prefixes) else outside)[f] += 1
    return outside.most_common(), churn.most_common()


def test_landscape(repo: Path, files: list[str], nearby: list[str], paths: list[str]) -> str:
    tests = [f for f in files if TEST_PATH.search(f)]
    nearby_tests = sorted({f for f in nearby if TEST_PATH.search(f)})
    targets = []
    for build in [f for f in files if Path(f).name in BUILD_NAMES]:
        pkg = str(Path(build).parent)
        targets += [f"//{pkg}:{name} ({rule})" for rule, name in BAZEL_TEST_RULE.findall((repo / build).read_text(errors="replace"))]
    fixtures = []
    for conftest in [f for f in tests + nearby_tests if f.endswith("conftest.py")]:
        try:
            tree = ast.parse((repo / conftest).read_text(errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and any("fixture" in ast.unparse(d) for d in n.decorator_list)]
        if names:
            fixtures.append(f"{conftest}: {', '.join(names)}")
    ci = git(repo, "grep", "-l", "-F", *[x for p in paths for x in ("-e", p)], "--",
             ".github/workflows", ".buildkite", ".circleci", ".gitlab-ci.yml").split()
    sections = [
        ("Test files in the area", tests[:60]),
        ("Tests elsewhere that import or co-change with the area", nearby_tests[:40]),
        ("Bazel test targets", targets[:60]),
        ("Pytest fixtures", fixtures),
        ("CI configs mentioning the area", ci),
    ]
    return "\n\n".join(f"{title}:\n" + ("\n".join(f"- {x}" for x in items) or "(none)") for title, items in sections)


# ---------------------------------------------------------------- docs and history


def ancestor_dirs(repo: Path, anchors: list[str]) -> list[str]:
    dirs = set()
    for anchor in anchors:
        path = Path(anchor)
        start = path if (repo / path).is_dir() else path.parent
        dirs.update(str(d) for d in [start, *start.parents])
    return sorted(dirs, key=lambda s: (-1 if s == "." else s.count("/"), s))


def gather_docs(repo: Path, anchors: list[str]) -> dict:
    """Guides, READMEs, and OWNERS on every ancestor (inlined); other docs and style configs (listed)."""
    guides, readmes, owners, listed, configs = {}, {}, {}, [], []

    def read(base: Path, names: tuple[str, ...], into: dict, limit: int) -> None:
        for name in names:
            f = base / name
            if f.is_file():
                into[str(f.relative_to(repo))] = clip(f.read_text(errors="replace"), limit)

    for d in ancestor_dirs(repo, anchors):
        base = repo / d
        read(base, GUIDE_NAMES, guides, MAX_GUIDE_CHARS)
        read(base, README_NAMES, readmes, MAX_README_CHARS)
        read(base, OWNER_NAMES, owners, MAX_OWNERS_CHARS)
        listed += [str((base / n).relative_to(repo)) for n in DOC_NAMES if (base / n).is_file()]
        configs += [str((base / n).relative_to(repo)) for n in STYLE_CONFIGS if (base / n).is_file()]
    # Markdown inside the touched dirs (design notes, module docs), plus a top-level docs/ tree.
    scoped = [a for a in anchors if a != "." and (repo / a).is_dir()] + ["docs"]
    inlined = set(guides) | set(readmes)
    listed += [p for p in tracked(repo, *[f"{s}/*.md" for s in scoped]) if p not in inlined]
    listed = list(dict.fromkeys(listed))
    return {"guides": guides, "readmes": readmes, "owners": owners, "docs": listed[:MAX_LISTED_DOCS],
            "docsDropped": max(0, len(listed) - MAX_LISTED_DOCS), "styleConfigs": configs}


def gather_history(repo: Path, anchors: list[str]) -> dict:
    out = git(repo, "log", f"-n{MAX_COMMITS}", "--no-merges", "--date=short", "--format=%H%x1f%an%x1f%ad%x1f%s",
              "HEAD", "--", *anchors)
    commits = []
    for line in out.splitlines():
        sha, author, date, subject = line.split("\x1f", 3)
        pr = re.search(r"\(#(\d+)\)\s*$", subject)
        commits.append({"sha": sha, "author": author, "date": date, "subject": subject,
                        "pr": int(pr.group(1)) if pr else None})
    owners = git(repo, "shortlog", "-sn", "--no-merges", "HEAD", "--", *anchors)
    return {"commits": commits, "owners": [line.strip() for line in owners.splitlines()[:8]]}
