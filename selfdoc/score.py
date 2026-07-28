"""Documentation quality scoring."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


CODE_EXTENSIONS = {
    "py", "go", "rs", "c", "cpp", "h", "hpp", "java", "rb", "kt",
    "js", "ts", "jsx", "tsx", "mjs", "cjs",
    "html", "css", "scss", "sass", "less", "svelte", "vue",
    "sh", "bash", "zsh", "fish",
    "makefile", "cmake", "dockerfile",
    "sql", "swift",
    "hcl", "tf", "nix", "proto", "graphql",
    "gd", "gdshader",
}

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "__pycache__", "vendor",
    "dist", "build", ".next", "out", ".cache", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

SKIP_MD_FILES = {"CHANGELOG.md"}

TIERS = {
    0: ("None", "No markdown documentation"),
    1: ("Basic", "Has markdown documentation"),
    2: ("Selfdoc", "selfdoc.json configured"),
    3: ("Templates", "Auto-generated root files (README/CLAUDE)"),
    4: ("Directives", "Directives connect docs to source code"),
    5: ("Advanced", "Custom directives or blog posts"),
}

NEXT_STEPS = {
    0: "Create a README.md with project description and usage",
    1: "Run `selfdoc init` to create selfdoc.json",
    2: "Add docs/_README.md to root_files in selfdoc.json",
    3: "Use :-: directives in docs/ to connect docs to source code",
    4: "Define custom directives or configure blog posts",
}

TABLE_NEXT_STEPS = {
    0: "create README.md",
    1: "selfdoc init",
    2: "add root_files templates",
    3: "add :-: directives",
    4: "custom directives / blog",
    5: "--",
}


def check_dirstat():
    try:
        subprocess.run(
            ["dirstat", "scan", "--help"],
            capture_output=True,
        )
    except FileNotFoundError:
        print("error: dirstat is not installed", file=sys.stderr)
        print(
            "install: go install github.com/smm-h/dirstat/cmd/dirstat@latest",
            file=sys.stderr,
        )
        sys.exit(1)


def get_submodule_paths(project_path):
    try:
        gitmodules = Path(project_path) / ".gitmodules"
        if not gitmodules.is_file():
            return []
        text = gitmodules.read_text()
        return re.findall(r"^\s*path\s*=\s*(.+)$", text, re.MULTILINE)
    except Exception:
        return []


def get_code_loc(project_path, submodule_paths=None):
    try:
        result = subprocess.run(
            [
                "dirstat", "scan", str(project_path),
                "--output", "json",
                "--type", "text",
                "--stats", "count",
                "--stats", "total-loc",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = json.loads(result.stdout)
        code_loc = 0
        code_files = 0
        for group in data.get("groups", []):
            fmt = group.get("format", "").lower()
            if fmt in CODE_EXTENSIONS:
                code_loc += group.get("total_loc", 0)
                code_files += group.get("count", 0)

        if submodule_paths:
            for sp in submodule_paths:
                sub_dir = Path(project_path) / sp
                if not sub_dir.is_dir():
                    continue
                try:
                    sub_result = subprocess.run(
                        [
                            "dirstat", "scan", str(sub_dir),
                            "--output", "json",
                            "--type", "text",
                            "--stats", "count",
                            "--stats", "total-loc",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    sub_data = json.loads(sub_result.stdout)
                    for group in sub_data.get("groups", []):
                        fmt = group.get("format", "").lower()
                        if fmt in CODE_EXTENSIONS:
                            code_loc -= group.get("total_loc", 0)
                            code_files -= group.get("count", 0)
                except Exception:
                    pass

        return (code_loc, code_files)
    except Exception:
        return (0, 0)


def count_markdown(project_path, submodule_paths=None):
    doc_loc = 0
    doc_files = 0
    submodule_abs = set()
    if submodule_paths:
        for sp in submodule_paths:
            submodule_abs.add(str(Path(project_path) / sp))

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS
            and d != "todo"
            and os.path.join(root, d) not in submodule_abs
        ]
        for fname in files:
            if not fname.endswith(".md"):
                continue
            if fname in SKIP_MD_FILES:
                continue
            full_path = os.path.join(root, fname)
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                doc_loc += len(lines)
                doc_files += 1
            except Exception:
                pass

    return (doc_loc, doc_files)


def get_selfdoc_info(project_path):
    selfdoc_json = Path(project_path) / "selfdoc.json"
    if not selfdoc_json.is_file():
        return {"has_selfdoc": False}

    try:
        config = json.loads(selfdoc_json.read_text())
    except Exception:
        return {"has_selfdoc": False}

    root_files = config.get("root_files", [])
    auto_readme = any(rf.endswith("_README.md") for rf in root_files)
    auto_claude = any(rf.endswith("_CLAUDE.md") for rf in root_files)

    directives_dict = config.get("directives", {})
    custom_directives = len(directives_dict) if isinstance(directives_dict, dict) else 0

    has_posts = bool(config.get("posts"))

    docs_dir = Path(project_path) / config.get("docs", "docs")
    directive_count = 0
    if docs_dir.is_dir():
        for root, dirs, files in os.walk(docs_dir):
            dirs[:] = [d for d in dirs if d != "_build"]
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                full_path = os.path.join(root, fname)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if ":-:" in line or ":<:" in line or ":>:" in line:
                                directive_count += 1
                except Exception:
                    pass

    return {
        "has_selfdoc": True,
        "auto_readme": auto_readme,
        "auto_claude": auto_claude,
        "custom_directives": custom_directives,
        "has_posts": has_posts,
        "directive_count": directive_count,
    }


def compute_tier(doc_loc, selfdoc_info):
    if doc_loc == 0:
        return 0
    if not selfdoc_info.get("has_selfdoc"):
        return 1
    if not selfdoc_info.get("auto_readme"):
        return 2
    if not selfdoc_info.get("directive_count"):
        return 3
    if not selfdoc_info.get("custom_directives") and not selfdoc_info.get("has_posts"):
        return 4
    return 5


def score_project(project_path):
    project_path = Path(project_path)
    submodule_paths = get_submodule_paths(project_path)
    code_loc, code_files = get_code_loc(project_path, submodule_paths)
    doc_loc, doc_files = count_markdown(project_path, submodule_paths)
    selfdoc_info = get_selfdoc_info(project_path)
    tier = compute_tier(doc_loc, selfdoc_info)

    return {
        "project": project_path.name,
        "path": str(project_path),
        "tier": tier,
        "tier_name": TIERS[tier][0],
        "code_loc": code_loc,
        "doc_loc": doc_loc,
        "doc_files": doc_files,
        "doc_ratio": round(doc_loc / code_loc, 4) if code_loc > 0 else None,
        "selfdoc": selfdoc_info,
        "next_step": NEXT_STEPS.get(tier),
    }


def discover_projects(scan_dir):
    projects = []
    scan_path = Path(scan_dir)
    for entry in sorted(scan_path.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / ".rlsbl").is_dir() or (entry / ".rlsbl-monorepo").is_dir():
            projects.append(entry)
    return projects


def format_single_text(result):
    lines = []
    tier = result["tier"]
    lines.append(
        f"{result['project']} -- Tier {tier} / 5 ({result['tier_name']})"
    )
    lines.append("")

    code_loc = f"{result['code_loc']:,}"
    doc_loc = f"{result['doc_loc']:,}"
    if result["code_loc"] > 0:
        ratio = f"{result['doc_ratio'] * 100:.1f}%"
    else:
        ratio = "n/a"
    lines.append(
        f"{code_loc} code LOC | {doc_loc} doc LOC ({ratio}) | "
        f"{result['doc_files']} files"
    )

    lines.append("")
    selfdoc = result["selfdoc"]
    if selfdoc.get("has_selfdoc"):
        lines.append("Selfdoc:")
        lines.append(
            f"  Auto-generated README    "
            f"{'yes' if selfdoc.get('auto_readme') else 'no'}"
        )
        lines.append(
            f"  Auto-generated CLAUDE    "
            f"{'yes' if selfdoc.get('auto_claude') else 'no'}"
        )
        lines.append(
            f"  Custom directives        "
            f"{selfdoc.get('custom_directives') or '-'}"
        )
        lines.append(
            f"  Blog posts               "
            f"{'yes' if selfdoc.get('has_posts') else 'no'}"
        )
        lines.append(
            f"  Directive uses           "
            f"{selfdoc.get('directive_count') or '-'}"
        )
    else:
        lines.append("Selfdoc: not configured")

    if tier > 0:
        lines.append("")
        lines.append("Completed:")
        for t in range(1, tier + 1):
            lines.append(f"  Tier {t} -- {TIERS[t][1]}")

    if tier < 5:
        lines.append("")
        lines.append("To do:")
        for t in range(tier + 1, 6):
            if t == tier + 1:
                lines.append(f"  Tier {t} -- {NEXT_STEPS[tier]}")
            else:
                lines.append(f"  Tier {t} -- {TIERS[t][1]}")
    elif tier == 5:
        lines.append("")
        lines.append("All tiers complete.")

    return "\n".join(lines)


def format_multi_text(results):
    lines = []
    lines.append(f"{len(results)} projects scanned")
    lines.append("")

    name_width = max(len(r["project"]) for r in results) if results else 7

    header = (
        f"{'Project':<{name_width}}  {'Tier':>5}  {'Code LOC':>10}  "
        f"{'Doc LOC':>9}  {'Ratio':>7}  Next Step"
    )
    lines.append(header)
    lines.append("-" * len(header))

    sorted_results = sorted(
        results,
        key=lambda r: (r["tier"], r["doc_ratio"] if r["doc_ratio"] is not None else -1),
    )

    for r in sorted_results:
        tier_str = f"{r['tier']}/5"
        code_str = f"{r['code_loc']:,}"
        doc_str = f"{r['doc_loc']:,}"
        if r["doc_ratio"] is not None:
            ratio_str = f"{r['doc_ratio'] * 100:.1f}%"
        else:
            ratio_str = "n/a"
        next_step = TABLE_NEXT_STEPS.get(r["tier"], "--")
        lines.append(
            f"{r['project']:<{name_width}}  {tier_str:>5}  {code_str:>10}  "
            f"{doc_str:>9}  {ratio_str:>7}  {next_step}"
        )

    return "\n".join(lines)


def format_json(data):
    return json.dumps(data, indent=2)


def run_score(scan=None, format="text"):
    check_dirstat()

    if scan is not None:
        projects = discover_projects(scan)
        if not projects:
            print(f"No rlsbl-managed projects found in {scan}", file=sys.stderr)
            return 1

        results = [score_project(p) for p in projects]
        results.sort(
            key=lambda r: (
                r["tier"],
                r["doc_ratio"] if r["doc_ratio"] is not None else -1,
            ),
        )

        if format == "json":
            output = {
                "scan_dir": str(scan),
                "count": len(results),
                "projects": results,
            }
            print(format_json(output))
        else:
            print(format_multi_text(results))
    else:
        result = score_project(Path.cwd())
        if format == "json":
            print(format_json(result))
        else:
            print(format_single_text(result))

    return 0
