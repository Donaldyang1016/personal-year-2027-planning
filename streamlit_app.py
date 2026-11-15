"""Personal Year 2027 — Streamlit MVP.

Plan definitions live in data/goals.json (version-controlled).
User updates live in session memory until explicitly exported to JSON.
"""
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Personal Year 2027", page_icon="🎯", layout="wide")
BASE = Path(__file__).parent
PLAN = json.loads((BASE / "data" / "goals.json").read_text(encoding="utf-8"))
GOALS = PLAN["goals"]
GOAL_BY_ID = {g["id"]: g for g in GOALS}
STATUSES = ["Not started", "In progress", "At risk", "Completed", "Paused"]

st.markdown("""<style>
.block-container {padding-top: 1.7rem; max-width: 1250px;}
[data-testid="stMetric"] {background: rgba(128,128,128,.07); border: 1px solid rgba(128,128,128,.13); border-radius: 12px; padding: 14px;}
h1 {letter-spacing:-.035em;} h2 {letter-spacing:-.025em;}
</style>""", unsafe_allow_html=True)

if "records" not in st.session_state:
    st.session_state.records = {g["id"]: {"status": "Not started", "progress": 0, "notes": "", "updated_at": ""} for g in GOALS}
if "activity" not in st.session_state:
    st.session_state.activity = []


def export_payload():
    return {"schema_version": 1, "exported_at": datetime.now().isoformat(timespec="seconds"),
            "records": st.session_state.records, "activity": st.session_state.activity}


def import_payload(blob):
    if not isinstance(blob, dict) or blob.get("schema_version") != 1:
        raise ValueError("Unsupported backup format")
    raw = blob.get("records")
    if not isinstance(raw, dict):
        raise ValueError("Missing records")
    for key, item in raw.items():
        if key not in GOAL_BY_ID or not isinstance(item, dict):
            continue
        status = item.get("status", "Not started")
        progress = item.get("progress", 0)
        if status not in STATUSES or not isinstance(progress, int) or not 0 <= progress <= 100:
            raise ValueError(f"Invalid record for {key}")
        st.session_state.records[key] = {
            "status": status, "progress": progress,
            "notes": str(item.get("notes", ""))[:20000],
            "updated_at": str(item.get("updated_at", ""))[:32],
        }
    activity = blob.get("activity", [])
    if isinstance(activity, list):
        st.session_state.activity = [x for x in activity if isinstance(x, dict)][:1000]


def render_goal(g, show_quarters=False):
    r = st.session_state.records[g["id"]]
    with st.expander(f"{g['id']} · {g['title']}  |  {r['status']}", expanded=False):
        st.caption(f"{g['section']} · {g['priority']} · Target date: {g['due']}")
        st.markdown(f"**Must:** {g['must']}\n\n**Target:** {g['target']}\n\n**Stretch:** {g['stretch']}")
        if show_quarters:
            st.table(pd.DataFrame([{"Quarter": k, "Milestone": v} for k, v in g["quarterly"].items()]).set_index("Quarter"))
        st.progress(r["progress"] / 100, text=f"Self-reported progress · {r['progress']}%")
        if r["notes"]:
            st.caption(f"Latest note: {r['notes']}")


with st.sidebar:
    st.title("🎯 Personal Year 2027")
    st.caption("Planning & Progress · MVP V0.1")
    st.divider()
    st.info("Plan: GitHub source files. Tracker: temporary session state. Export a backup before closing the app.")
    st.download_button("⬇️ Export tracker backup", data=json.dumps(export_payload(), ensure_ascii=False, indent=2),
                       file_name=f"personal-year-tracker-{date.today().isoformat()}.json", mime="application/json", use_container_width=True)
    upload = st.file_uploader("Restore tracker backup", type=["json"])
    if upload is not None:
        if st.button("Import this backup", use_container_width=True):
            try:
                import_payload(json.load(upload))
                st.success("Backup restored")
                st.rerun()
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                st.error(f"Could not import backup: {exc}")

st.title("Personal Year 2027")
st.caption("From annual vision to weekly action — one personal goal management dashboard")

tabs = st.tabs(["🏠 Home", "🎯 Annual", "📅 Quarterly", "🗓️ Monthly", "✅ Weekly", "📈 Tracker"])

with tabs[0]:
    complete = sum(r["status"] == "Completed" for r in st.session_state.records.values())
    progress = round(sum(r["progress"] for r in st.session_state.records.values()) / max(len(GOALS), 1))
    a, b, c, d = st.columns(4)
    a.metric("Life domains", len(PLAN["domains"]))
    b.metric("Documented goals", len(GOALS))
    c.metric("Completed goals", complete)
    d.metric("D01 self-reported progress", f"{progress}%")
    st.subheader("Highlighted goals")
    for g in GOALS[:4]:
        render_goal(g)
    st.subheader("12 life domains")
    df = pd.DataFrame(PLAN["domains"])
    st.dataframe(df.rename(columns={"id":"Domain", "name":"Name", "status":"Planning status"}), hide_index=True, use_container_width=True)
    st.caption("Only D01 contains the detailed draft. Other domain names will be added after their approved plans are available.")

with tabs[1]:
    st.header("Annual goals")
    domain = st.selectbox("Domain", [d["id"] for d in PLAN["domains"]],
                          format_func=lambda x: f"{x} · {next(d['name'] for d in PLAN['domains'] if d['id']==x)}")
    items = [g for g in GOALS if g["domain"] == domain]
    if not items:
        st.info("Annual plan not added yet. Add its structured goals to data/goals.json.")
    for g in items:
        render_goal(g, show_quarters=True)

with tabs[2]:
    st.header("Quarterly milestones")
    quarter = st.segmented_control("Choose quarter", ["Q1", "Q2", "Q3", "Q4"], default="Q1")
    qrows = [{"Goal": g["id"], "Objective": g["title"], "Milestone": g["quarterly"].get(quarter, ""),
              "Status": st.session_state.records[g["id"]]["status"]} for g in GOALS]
    st.dataframe(pd.DataFrame(qrows), hide_index=True, use_container_width=True)
    st.caption("Milestones are drafted targets; their status is currently shared with the annual goal. Separate quarterly tracking can be added in V0.2.")

with tabs[3]:
    st.header("Monthly goals")
    st.info("Monthly goals have not been defined yet. This section is ready for the next planning layer.")
    st.markdown("**Future structure:** month → domain → monthly outcome → due date → evidence → status.")
    st.caption("We will not invent monthly targets before reviewing the annual and quarterly plans.")

with tabs[4]:
    st.header("Weekly goals")
    st.info("Weekly goals have not been defined yet. This section is ready for the weekly planning layer.")
    st.markdown("**Future structure:** week start → tasks → linked monthly goal → estimated hours → completed / postponed.")

with tabs[5]:
    st.header("Progress tracker")
    st.caption("Update a goal below. This state is temporary: export a JSON backup to preserve your changes.")
    selection = st.selectbox("Goal", [g["id"] for g in GOALS], format_func=lambda x: f"{x} · {GOAL_BY_ID[x]['title']}")
    current = st.session_state.records[selection]
    with st.form(f"tracker_form_{selection}"):
        status = st.selectbox("Status", STATUSES, index=STATUSES.index(current["status"]))
        progress = st.slider("Estimated progress (%)", 0, 100, value=current["progress"])
        notes = st.text_area("Evidence / progress notes", value=current["notes"], height=120)
        saved = st.form_submit_button("Save progress", type="primary")
    if saved:
        stamp = datetime.now().isoformat(timespec="seconds")
        st.session_state.records[selection] = {"status": status, "progress": progress,
                                                "notes": notes, "updated_at": stamp}
        st.session_state.activity.insert(0, {"goal_id": selection, "status": status,
                                              "progress": progress, "notes": notes, "date": stamp})
        st.success("Updated in this session. Export a JSON backup to keep it.")
    summary = pd.DataFrame([{"Goal": g["id"], "Title": g["title"],
                             "Status": st.session_state.records[g["id"]]["status"],
                             "Progress (%)": st.session_state.records[g["id"]]["progress"]} for g in GOALS])
    st.subheader("All tracked goals")
    st.dataframe(summary, hide_index=True, use_container_width=True)
    if st.session_state.activity:
        st.subheader("Recent activity")
        st.dataframe(pd.DataFrame(st.session_state.activity[:20]), hide_index=True, use_container_width=True)
