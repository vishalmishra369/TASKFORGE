"""Compatibility checks that need optional packages (skipped when absent)."""
from pathlib import Path

import pytest

from taskforge.config import load_config
from taskforge.packager import harbor_name, package


def test_harbor_name_strips_leading_underscore():
    assert harbor_name("_golden") == "golden" and harbor_name("click-x") == "click-x"


def test_generated_package_loads_in_real_harbor(tmp_path):
    pytest.importorskip("harbor")
    from harbor.models.task.task import Task

    cfg = load_config("config.yaml")
    for tid in ("click-duration-type", "_golden"):
        td = package(cfg, tid, "new_param_type", "# T", "diff\n", "def test_a(): pass\n",
                     ["tests/test_taskforge_feature.py::test_a"], ["tests/t.py::t"], out_root=tmp_path)
        t = Task(td)
        assert t.config.task.name.startswith(cfg.task_namespace + "/")


def test_golden_task_loads_in_real_harbor():
    pytest.importorskip("harbor")
    from harbor.models.task.task import Task

    assert Task(Path("tasks/_golden").resolve()).config.task.name == "hedgeforge/golden"


def test_dashboard_starts_without_errors():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path("dashboard/app.py").resolve()), default_timeout=60).run()
    assert not at.exception
