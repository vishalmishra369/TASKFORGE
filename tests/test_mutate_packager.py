import json
from pathlib import Path

from taskforge.config import load_config
from taskforge.mutate import generate_mutants, reward_from
from taskforge.packager import lint_instruction, package

PATCH = '''diff --git a/src/pkg/a.py b/src/pkg/a.py
--- a/src/pkg/a.py
+++ b/src/pkg/a.py
@@ -1,2 +1,12 @@
 import x
+class Foo:
+    """Docstring with and/or words,
+    and a 5 and True inside.
+    """
+
+    def go(self, v):
+        if v is not None and v > 3:
+            self.fail("bad value", 1)
+        return v
'''


def test_mutants_skip_docstrings_and_keep_line_count():
    ms = generate_mutants(PATCH, 10)
    assert ms, "expected mutants"
    for m in ms:
        assert len(m["patch"].splitlines()) == len(PATCH.splitlines())
        assert "Docstring" not in m["desc"] and "and a 5" not in m["desc"]
    kinds = " ".join(m["desc"] for m in ms)
    assert "boundary" in kinds and "return None" in kinds and "error message" in kinds


def test_mutants_deterministic():
    assert [m["desc"] for m in generate_mutants(PATCH)] == [m["desc"] for m in generate_mutants(PATCH)]


def test_reward_rule():
    assert reward_from({"p": "passed", "f1": "passed", "f2": "failed"}, ["f1", "f2"], ["p"]) == 0.5
    assert reward_from({"p": "failed", "f1": "passed"}, ["f1"], ["p"]) == 0.0
    assert reward_from({}, [], []) == 0.0


def test_lint_catches_leaks_and_missing_sections():
    assert lint_instruction("# T\nrun pytest and test_feature.py")
    ok = "\n".join(f"## {s}\ntext" for s in ["Background", "Requirements", "Errors", "Examples", "Out of scope"])
    assert lint_instruction("# T\n" + ok) == []


def test_package_layout(tmp_path):
    cfg = load_config("config.yaml")
    td = package(cfg, "click-x", "new_param_type", "# T", "diff\n", "def test_a(): pass\n",
                 ["tests/test_taskforge_feature.py::test_a"], ["tests/t.py::t"], out_root=tmp_path)
    files = {str(p.relative_to(td)) for p in td.rglob("*") if p.is_file()}
    assert files == {"instruction.md", "task.toml", "environment/Dockerfile", "solution/solve.sh",
                     "solution/solution.patch", "tests/test.sh", "tests/run_eval.py", "tests/test_feature.py",
                     "tests/fail_to_pass.json", "tests/pass_to_pass.json"}
    assert cfg.base_commit in (td / "task.toml").read_text()
    assert f"git checkout {cfg.base_commit}" in (td / "environment/Dockerfile").read_text()
    assert json.loads((td / "tests/fail_to_pass.json").read_text()) == ["tests/test_taskforge_feature.py::test_a"]
    assert (td / "tests/test.sh").stat().st_mode & 0o111
