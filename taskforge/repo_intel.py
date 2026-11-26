"""Step 3: Repo Intelligence. Pure `ast` analysis of the package, cached per base_commit."""
from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path


def _first_line(node) -> str:
    d = ast.get_docstring(node) or ""
    return d.strip().splitlines()[0] if d.strip() else ""


def _sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        return f"{fn.name}({ast.unparse(fn.args)})"
    except Exception:
        return f"{fn.name}(...)"


def _bare(base: str) -> str:
    """'t.Generic[X]' -> 'Generic', 'ParamType[str]' -> 'ParamType' (click 8.5 types are generic)."""
    return base.split("[")[0].split(".")[-1]


def _base_names(cls: ast.ClassDef) -> list[str]:
    out = []
    for b in cls.bases:
        try:
            out.append(ast.unparse(b))
        except Exception:
            pass
    return out


def _parse_module(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes, funcs = [], []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            methods = [
                {"sig": _sig(m), "doc": _first_line(m)}
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                and (not m.name.startswith("_") or m.name == "__init__")
            ]
            classes.append({"name": node.name, "bases": _base_names(node), "doc": _first_line(node),
                            "methods": methods, "line": node.lineno})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            funcs.append({"sig": _sig(node), "name": node.name, "doc": _first_line(node), "line": node.lineno})
    return {"classes": classes, "functions": funcs}


def _identifiers(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    ids: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            ids.add(n.id)
        elif isinstance(n, ast.Attribute):
            ids.add(n.attr)
        elif isinstance(n, ast.ImportFrom) and n.module:
            ids.add(n.module.split(".")[-1])
    return ids


def build_repo_map(repo: Path, package_dir: str = "src/click", tests_dir: str = "tests") -> dict:
    pkg = repo / package_dir
    modules: dict[str, dict] = {}
    for f in sorted(pkg.glob("*.py")):
        if f.name.startswith("_") and f.name != "__init__.py":
            continue
        modules[f.stem] = _parse_module(f)

    # ParamType subclasses (transitive)
    all_classes = {c["name"]: (m, c) for m, d in modules.items() for c in d["classes"]}
    param_types, frontier = [], {"ParamType"}
    changed = True
    while changed:
        changed = False
        for name, (mod, c) in all_classes.items():
            if name not in frontier and any(_bare(b) in frontier for b in c["bases"]):
                frontier.add(name)
                changed = True
    for name in sorted(frontier - {"ParamType"}):
        mod, c = all_classes[name]
        param_types.append({"name": name, "module": mod, "doc": c["doc"]})

    def init_sig(cls_name: str) -> str:
        item = all_classes.get(cls_name)
        if not item:
            return ""
        for m in item[1]["methods"]:
            if m["sig"].startswith("__init__"):
                return m["sig"]
        return ""

    help_funcs = [
        f"{m}.{c['name']}.{x['sig']}" for m, d in modules.items() for c in d["classes"]
        for x in c["methods"] if x["sig"].startswith(("format_", "get_help"))
    ] + [f"formatting.{f['sig']}" for f in modules.get("formatting", {}).get("functions", [])]

    # test map: which test files touch which module's public names
    tests = repo / tests_dir
    test_files = sorted(tests.rglob("test_*.py")) if tests.exists() else []
    ident = {tf: _identifiers(tf) for tf in test_files}
    test_map: dict[str, list[str]] = {}
    conv = Counter()
    for mod, d in modules.items():
        names = {c["name"] for c in d["classes"]} | {f["name"] for f in d["functions"]}
        scored = sorted(((len(names & ident[tf]), tf) for tf in test_files), reverse=True)
        test_map[mod] = [str(tf.relative_to(repo)) for s, tf in scored[:5] if s > 0]
    for tf in test_files:
        txt = tf.read_text(encoding="utf-8", errors="ignore")
        conv["CliRunner"] += txt.count("CliRunner") + txt.count("runner.invoke")
        conv["pytest.raises"] += txt.count("pytest.raises")
        conv["def test_"] += txt.count("def test_")
        conv["parametrize"] += txt.count("parametrize")
    src_txt = "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in pkg.glob("*.py"))
    conventions = {
        "error_usage": {
            "BadParameter": src_txt.count("BadParameter"), "UsageError": src_txt.count("UsageError"),
            "self.fail(": src_txt.count("self.fail("),
        },
        "tests": {"test_files": len(test_files), **dict(conv)},
        "style": "tests are plain pytest functions named test_*, use CliRunner and "
                 "pytest.raises(click.<Error>); types raise self.fail(msg, param, ctx)",
    }
    return {
        "package_dir": package_dir,
        "modules": modules,
        "param_types": param_types,
        "option_init": init_sig("Option"),
        "argument_init": init_sig("Argument"),
        "command_init": init_sig("Command"),
        "group_init": init_sig("Group"),
        "help_formatting": help_funcs,
        "test_map": test_map,
        "conventions": conventions,
    }


def load_or_build(repo: Path, base_commit: str, cache_dir: Path, **kw) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"repo_map_{base_commit}.json"
    if cf.exists():
        return json.loads(cf.read_text())
    m = build_repo_map(repo, **kw)
    cf.write_text(json.dumps(m, indent=1))
    return m


def public_names(repo_map: dict) -> dict[str, set[str]]:
    """Public names by kind: classes, functions (module level), methods. Used by the novelty filter."""
    out: dict[str, set[str]] = {"classes": set(), "functions": set(), "methods": set()}
    for d in repo_map["modules"].values():
        for c in d["classes"]:
            out["classes"].add(c["name"])
            out["methods"] |= {m["sig"].split("(")[0] for m in c["methods"]}
        out["functions"] |= {f["name"] for f in d["functions"]}
    return out


def summarize_for_prompt(repo_map: dict, max_chars: int = 12000) -> str:
    """Compact text version for LLM prompts, highest-value parts first."""
    lines = ["# click repo summary", f"Option.{repo_map['option_init']}", f"Argument.{repo_map['argument_init']}",
             f"Command.{repo_map['command_init']}", f"Group.{repo_map['group_init']}", "",
             "## ParamType subclasses (new types should look like these)"]
    lines += [f"- {p['name']} ({p['module']}): {p['doc']}" for p in repo_map["param_types"]]
    lines += ["", "## Help formatting hooks"] + [f"- {h}" for h in repo_map["help_formatting"][:25]]
    lines += ["", "## Conventions", json.dumps(repo_map["conventions"])]
    lines += ["", "## Public API by module"]
    for mod, d in repo_map["modules"].items():
        cl = ", ".join(c["name"] for c in d["classes"])
        fn = ", ".join(f["name"] for f in d["functions"])
        lines.append(f"- {mod}: classes[{cl}] functions[{fn}]")
        if repo_map["test_map"].get(mod):
            lines.append(f"    tests: {', '.join(repo_map['test_map'][mod][:3])}")
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[: max_chars - 20] + "\n...[truncated]"
