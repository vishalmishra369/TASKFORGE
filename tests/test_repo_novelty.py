from taskforge.novelty import filter_and_rank, similarity
from taskforge.repo_intel import build_repo_map, summarize_for_prompt


def make_pkg(tmp_path):
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "types.py").write_text(
        'class ParamType:\n    """Base."""\n\nclass Color(ParamType[str]):\n    """A color."""\n'
        '    def convert(self, value, param, ctx):\n        return value\n')
    (src / "core.py").write_text(
        'class Option:\n    def __init__(self, name, hidden=False):\n        pass\n\ndef helper_thing():\n    pass\n')
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_types.py").write_text("from pkg.types import Color\n\ndef test_a():\n    Color()\n")
    (tmp_path / "CHANGES.md").write_text("Added fancy_widget support\n")
    return tmp_path


def test_repo_map_finds_generic_paramtype_subclass(tmp_path):
    m = build_repo_map(make_pkg(tmp_path), package_dir="src/pkg")
    assert [p["name"] for p in m["param_types"]] == ["Color"]
    assert m["test_map"]["types"] == ["tests/test_types.py"]
    assert "Color" in summarize_for_prompt(m, 500) or len(summarize_for_prompt(m, 500)) <= 500


def cand(title, names, api="x", lines=100, arch="a"):
    return dict(archetype=arch, title=title, api_sketch=api, behaviours=["a", "b", "c"],
                edge_cases=["x", "y"], est_lines=lines, new_names=names)


def test_novelty_rejects_existing_and_dupes(tmp_path):
    repo = make_pkg(tmp_path)
    m = build_repo_map(repo, package_dir="src/pkg")
    kept, rej = filter_and_rank(
        [cand("new", ["Brand_new_thing"]), cand("old class", ["Color"]), cand("old func", ["helper_thing"]),
         cand("old doc", ["fancy_widget"]), cand("kwarg", ["hidden"]), cand("huge", ["ZetaType"], lines=900)],
        repo, m, check_upstream=False)
    assert [c["title"] for c in kept] == ["new"]
    assert {r["title"] for r in rej} == {"old class", "old func", "old doc", "kwarg", "huge"}


def test_similarity_and_dedupe(tmp_path):
    repo = make_pkg(tmp_path)
    m = build_repo_map(repo, package_dir="src/pkg")
    a = cand("duration type parser", ["DurationA"], api="parse duration strings seconds minutes hours")
    b = cand("duration type parsing", ["DurationB"], api="parse duration strings seconds minutes hours")
    assert similarity(a, b) > 0.6
    kept, rej = filter_and_rank([a, b], repo, m, check_upstream=False)
    assert len(kept) == 1 and len(rej) == 1
