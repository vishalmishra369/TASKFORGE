"""Step 5: novelty filter + scoring. Heuristic and deterministic (no LLM calls).

A candidate is rejected when:
  * one of its `new_names` already exists in click's public API / Option|Command kwargs,
  * a distinctive name appears in the changelog, docs, or source text,
  * the same name exists on upstream main (when the clone has network),
  * it overlaps too much with a better-scored candidate (token Jaccard > threshold).
"""
from __future__ import annotations

import re
from pathlib import Path

from .gitutil import run
from .repo_intel import public_names

STOP = {"help", "type", "name", "value", "default", "option", "command", "group", "click", "param"}
CHANGELOGS = ("CHANGES.md", "CHANGES.rst")  # click 8.5.x uses CHANGES.md; older tags used .rst


def _distinctive(name: str) -> bool:
    return len(name) >= 6 and (("_" in name) or any(c.isupper() for c in name[1:]) or name[0].isupper())


def _kwarg_names(repo_map: dict) -> set[str]:
    out: set[str] = set()
    for key in ("option_init", "argument_init", "command_init", "group_init"):
        out |= set(re.findall(r"(\w+)\s*(?::|=|,|\))", repo_map.get(key, "")))
    return out


def _tokens(c: dict) -> set[str]:
    txt = " ".join([c.get("title", ""), c.get("api_sketch", ""), *c.get("behaviours", [])])
    return {w for w in re.findall(r"[a-z_]{4,}", txt.lower()) if w not in STOP}


def similarity(a: dict, b: dict) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def score(c: dict) -> float:
    s = 0.0
    n = int(c.get("est_lines", 0) or 0)
    s += 0.35 if 40 <= n <= 300 else (0.1 if 20 <= n < 40 or 300 < n <= 450 else 0.0)
    s += 0.25 if 3 <= len(c.get("behaviours", [])) <= 8 else 0.1
    s += 0.2 if len(c.get("edge_cases", [])) >= 2 else 0.05
    s += 0.1 if c.get("api_sketch") else 0.0
    s += 0.1 if c.get("new_names") else 0.0
    return round(s, 3)


def check_existing(c: dict, repo: Path, repo_map: dict, check_upstream: bool = True) -> list[str]:
    """Return reasons the candidate already exists (empty list = looks novel)."""
    reasons: list[str] = []
    names = [n for n in c.get("new_names", []) if n and n.lower() not in STOP]
    api = public_names(repo_map)
    kw = _kwarg_names(repo_map)

    def in_api(n: str) -> bool:
        # CamelCase = a class; snake_case = function / keyword; methods only when distinctive (has "_")
        # (a bare word like "section" would collide with HelpFormatter.section and is checked as a kwarg only)
        if n[0].isupper():
            return n in api["classes"]
        return n in api["functions"] or n in kw or ("_" in n and n in api["methods"])
    src_text = "\n".join(p.read_text(errors="ignore") for p in (repo / repo_map["package_dir"]).glob("*.py"))
    docs_text = ""
    for cl in CHANGELOGS:
        if (repo / cl).exists():
            docs_text += (repo / cl).read_text(errors="ignore")
    if (repo / "docs").exists():
        docs_text += "\n".join(p.read_text(errors="ignore") for p in (repo / "docs").rglob("*.md"))
    for n in names:
        if in_api(n):
            reasons.append(f"'{n}' already in click public API / signatures")
        elif _distinctive(n) and re.search(rf"\b{re.escape(n)}\b", src_text):
            reasons.append(f"'{n}' already appears in click source")
        elif _distinctive(n) and re.search(rf"\b{re.escape(n)}\b", docs_text):
            reasons.append(f"'{n}' already appears in changelog/docs")
    if check_upstream and names:
        fetched = run(["git", "fetch", "-q", "origin", "main"], cwd=repo, timeout=120).returncode == 0
        if fetched:
            for n in names:
                if not _distinctive(n):
                    continue
                g = run(["git", "grep", "-q", "-w", n, "origin/main", "--", "src/click", "CHANGES.md", "docs"],
                        cwd=repo)
                if g.returncode == 0:
                    reasons.append(f"'{n}' exists on upstream main")
        else:
            reasons_note = "upstream check skipped (no network)"
            c.setdefault("notes", []).append(reasons_note)
    return reasons


SEM_SYSTEM = """You decide whether a proposed feature ALREADY EXISTS in the Python library `click` under any name. \
You get the proposal and evidence lines found in click's source, docs and changelog. Answer exists=true only if the \
evidence shows click already provides the same behaviour (even with different names or via an existing option). \
Features that merely sound similar but behave differently are NOT duplicates.
Return ONLY JSON: {"exists": true|false, "evidence": "short quote or reason"}."""


def _keywords(c: dict) -> list[str]:
    words = re.findall(r"[A-Za-z_]{5,}", " ".join([c.get("title", ""), c.get("api_sketch", ""),
                                                    *c.get("new_names", [])]))
    return list(dict.fromkeys(w.lower() for w in words if w.lower() not in STOP))[:10]


def evidence_lines(c: dict, repo: Path, package_dir: str = "src/click", limit: int = 30) -> list[str]:
    """grep-style lines mentioning the candidate's keywords in source, docs and changelog."""
    kws = _keywords(c)
    files = list((repo / package_dir).glob("*.py")) + list((repo / "docs").rglob("*.md")) \
        + [repo / n for n in CHANGELOGS if (repo / n).exists()]
    hits: list[str] = []
    for f in files:
        for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            low = line.lower()
            if any(k in low for k in kws):
                hits.append(f"{f.relative_to(repo)}:{i}: {line.strip()[:160]}")
                if len(hits) >= limit * 4:
                    break
    # prefer lines matching several keywords
    hits.sort(key=lambda h: -sum(k in h.lower() for k in kws))
    return hits[:limit]


def semantic_check(cfg, c: dict, repo: Path) -> str | None:
    """LLM duplicate check (critic model: independent family, local/free). Returns a reason or None.

    Fails open: an unreadable or failed answer never rejects a candidate (the heuristics and the human
    review still apply), it only records a note.
    """
    from .jsonutil import extract_json
    from .llm import call_llm
    ev = evidence_lines(c, repo, cfg.package_dir)
    user = (f"Proposal: {c.get('title')}\nAPI: {c.get('api_sketch')}\nBehaviours: {c.get('behaviours')}\n\n"
            f"Evidence from click ({len(ev)} lines):\n" + "\n".join(ev))
    try:
        d = extract_json(call_llm("novelty_semantic", SEM_SYSTEM, user, cfg.models.critic, json_mode=True,
                                  tag=c.get("title", "")))
    except Exception as ex:
        c.setdefault("notes", []).append(f"semantic novelty check unavailable: {ex}")
        return None
    return f"semantic: {d.get('evidence', 'already provided by click')}" if d.get("exists") is True else None


def filter_and_rank(candidates: list[dict], repo: Path, repo_map: dict, threshold: float = 0.6,
                    check_upstream: bool = True, semantic_cfg=None) -> tuple[list[dict], list[dict]]:
    """Returns (kept sorted best-first, rejected with reasons). Each candidate has 'archetype'."""
    for c in candidates:
        c["score"] = score(c)
    kept: list[dict] = []
    rejected: list[dict] = []
    for c in sorted(candidates, key=lambda x: -x["score"]):
        reasons = check_existing(c, repo, repo_map, check_upstream)
        for k in kept:
            sim = similarity(c, k)
            if sim > threshold:
                reasons.append(f"overlaps {sim:.2f} with '{k.get('title')}'")
        if int(c.get("est_lines", 0) or 0) > 450:
            reasons.append("too large for one patch")
        if not reasons and semantic_cfg is not None:  # only spend an LLM call on candidates that survived
            why = semantic_check(semantic_cfg, c, repo)
            if why:
                reasons.append(why)
        if reasons:
            rejected.append({**c, "rejected_reasons": reasons})
        else:
            kept.append(c)
    return kept, rejected


def best_per_archetype(kept: list[dict]) -> dict[str, list[dict]]:
    """archetype -> candidates best-first (index 0 is the pick, rest are spares for retries)."""
    out: dict[str, list[dict]] = {}
    for c in kept:
        out.setdefault(c["archetype"], []).append(c)
    return out
