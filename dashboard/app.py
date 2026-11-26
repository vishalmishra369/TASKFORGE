"""Read-only Streamlit viewer. Run:  streamlit run dashboard/app.py"""
import json
from pathlib import Path

import streamlit as st

try:
    from taskforge.review import status as review_status
except Exception:  # dashboard still works if the package is not installed
    review_status = None

ROOT = Path(__file__).resolve().parent.parent
TASKS, EVID = ROOT / "tasks", ROOT / "evidence"

st.set_page_config(page_title="TaskForge", layout="wide")
st.title("TaskForge: validated task packages")


def jload(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


rows = []
for d in sorted(p for p in TASKS.glob("*") if p.is_dir()):
    m = jload(d / "manifest.json") or {}
    g = m.get("gates", {})
    rows.append({
        "task": d.name, "archetype": m.get("archetype", "(golden/hand-made)" if d.name.startswith("_") else "?"),
        "nop": g.get("nop_is_0", {}).get("reward", "n/a"), "oracle": g.get("oracle_is_1", {}).get("reward", "n/a"),
        "mutants killed": f"{m['mutation']['kill_rate']:.0%}" if m.get("mutation") else "n/a",
        "retries": m.get("retries", "n/a"), "status": "ready" if m else "no manifest",
        "human review": (review_status(d) if review_status and m else "n/a"),
    })
if not rows:
    st.info("No tasks yet. Run `taskforge run --tasks 5`.")
    st.stop()
st.dataframe(rows, width="stretch")
if (EVID / "summary.md").exists():
    with st.expander("Latest run summary"):
        st.markdown((EVID / "summary.md").read_text())

with st.expander("Dropped candidates (evidence/failures.md)"):
    f = EVID / "failures.md"
    st.markdown(f.read_text() if f.exists() else "_No candidates dropped yet._")
with st.expander("Manual fixes (evidence/fixes.md)"):
    f = EVID / "fixes.md"
    st.markdown(f.read_text() if f.exists() else "_No manual fixes._")

pick = st.selectbox("Open a task", [r["task"] for r in rows])
d = TASKS / pick
tab1, tab2, tab3, tab4, tab5 = st.tabs(["instruction.md", "solution.patch", "feature tests", "validation", "manifest"])
tab1.markdown((d / "instruction.md").read_text())
tab2.code((d / "solution/solution.patch").read_text(), language="diff")
tab3.code((d / "tests/test_feature.py").read_text(), language="python")
ev = EVID / pick
if (ev / "validation.md").exists():
    tab4.markdown((ev / "validation.md").read_text())
if (ev / "mutation.json").exists():
    tab4.json(jload(ev / "mutation.json"))
for log in sorted(ev.rglob("harbor_console.log"))[:4]:
    with tab4.expander(str(log.relative_to(EVID))):
        st.code(log.read_text()[-4000:])
tab5.json(jload(d / "manifest.json") or {})
