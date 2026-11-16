"""Batch 1: strategic focus, habit counters, and verified outcome records.

No personal logs are stored in GitHub. Persistence requires PostgreSQL and a
private application password in Streamlit secrets. Unconfigured mode is read-only.
"""
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent
PERIODS = [
    ("Q1", "2026-11-16", "2027-01-03"),
    ("Q2", "2027-01-04", "2027-04-04"),
    ("Q3", "2027-04-05", "2027-07-04"),
    ("Q4", "2027-07-05", "2027-10-03"),
    ("Q5", "2027-10-04", "2028-01-02"),
]
D03_HABITS = [
    ("french-hours", "French study", 22, "hours"),
    ("market-am", "Morning market review", 5, "times"),
    ("market-pm", "Evening market review", 5, "times"),
    ("korean", "Korean study", 1, "sessions"),
]
D04_HABITS = [
    ("strength", "Strength training", 4, "times"),
    ("cardio", "Cardio", 2, "times"),
    ("weigh", "Morning weigh-ins", 4, "days"),
    ("waist", "Waist measurement", 1, "times"),
    ("nutrition", "Nutrition/protein logging", 7, "days"),
    ("sleep", "Workday sleep >=7.5h", 4, "nights"),
    ("mobility", "Post-training mobility", 4, "times"),
    ("weekly-review", "Weekly body/training review", 1, "times"),
]

def secrets_config():
    try:
        return (st.secrets.get("DATABASE_URL", ""), st.secrets.get("APP_PASSWORD", ""))
    except Exception:
        return "", ""

class PrivateStore:
    def __init__(self, dsn):
        import psycopg
        self.psycopg = psycopg
        self.dsn = dsn
        with self.psycopg.connect(self.dsn) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS batch1_records (
                record_key TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")
            conn.commit()

    def load(self, prefix):
        with self.psycopg.connect(self.dsn) as conn:
            rows = conn.execute(
                "SELECT record_key, payload FROM batch1_records WHERE record_key LIKE %s",
                (prefix + "%",)
            ).fetchall()
            return {key: payload for key, payload in rows}

    def save(self, key, payload):
        with self.psycopg.connect(self.dsn) as conn:
            conn.execute("""INSERT INTO batch1_records(record_key,payload,updated_at)
                VALUES (%s,%s::jsonb,NOW())
                ON CONFLICT(record_key) DO UPDATE SET
                payload=EXCLUDED.payload, updated_at=NOW()""",
                (key, json.dumps(payload, ensure_ascii=False)))
            conn.commit()

def quarter_at(d):
    for q, start, end in PERIODS:
        if date.fromisoformat(start) <= d <= date.fromisoformat(end):
            return q
    return "Q5" if d > date(2027, 10, 3) else "Q1"

def week_start(d):
    return d - timedelta(days=d.weekday())

def seven_day_qualifies(records, end_date, target):
    """Check an actual consecutive 7-day window, not seven scattered samples."""
    weights = {}
    for key, rec in records.items():
        if key.startswith("metric:D04:weight:"):
            day = key.rsplit(":", 1)[-1]
            try:
                weights[date.fromisoformat(day)] = float(rec["value"])
            except (ValueError, TypeError, KeyError):
                continue
    if not weights:
        return None
    earliest = min(weights)
    cursor = earliest + timedelta(days=6)
    best = None
    while cursor <= end_date:
        days = [cursor - timedelta(days=j) for j in range(7)]
        if all(day in weights for day in days):
            average = sum(weights[day] for day in days) / 7
            if average <= target:
                return {"end": cursor.isoformat(), "average": round(average, 2)}
            best = average
        cursor += timedelta(days=1)
    return {"best_complete_window_average": round(best, 2)} if best is not None else None

def render(store, plans):
    st.subheader("Batch 1 · D03–D05 Tracker")
    st.caption("Quarter Focus + concrete outcomes + repeatable habits · Monthly/Weekly task plans are not generated yet.")
    dsn, pw = secrets_config()
    if not dsn or not pw:
        st.warning("Read-only planning mode. Persistent tracking requires DATABASE_URL and APP_PASSWORD configured privately in Streamlit secrets. No records are saved in this mode.")
        access = False
    else:
        if not st.session_state.get("batch1_authorized"):
            attempt = st.text_input("Private tracking password", type="password", key="batch1_password")
            if st.button("Unlock private tracking", key="batch1_unlock"):
                if hmac.compare_digest(attempt, str(pw)):
                    st.session_state.batch1_authorized = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
        access = bool(st.session_state.get("batch1_authorized"))
        if access and store is None:
            try:
                store = PrivateStore(dsn)
            except Exception:
                st.error("Private database unavailable. Records were not saved.")
                access = False
    domain = st.selectbox("Domain", ["D03", "D04", "D05"], format_func=lambda d: {
        "D03":"D03 · Learning & Skills", "D04":"D04 · Health & Fitness",
        "D05":"D05 · Personal Image"}[d], key="batch1_domain")
    plan = plans.get(domain, {})
    today = date.today()
    chosen = st.date_input("Tracking date", value=today, min_value=date(2026,11,16), max_value=date(2028,1,2), key="batch1_date")
    q = quarter_at(chosen)
    records = store.load("") if access else {}
    st.markdown("### 1 · Quarterly strategic focus / 本季度重点")
    for goal in plan.get("goals", []):
        with st.expander(goal.get("title_zh", goal["id"])):
            st.write(goal.get("quarterly", {}).get(q, "Not specified"))
            st.caption("Qualitative focus; not a compulsory checkbox.")
            if goal.get("kpis"):
                for k in goal["kpis"]:
                    key = "outcome:" + k["id"]
                    verified = records.get(key, {}).get("verified", False)
                    st.write(("✅" if verified else "○") + " " + k["label"] + " · Target: " + str(k.get("target")) + " " + k.get("unit", ""))
    st.markdown("### 2 · Concrete verified outcomes / 实际成果")
    st.caption("Check only when independently evidenced. Completing weekly actions never automatically verifies an exam, paper, chapter, or appearance result.")
    if access:
        kpis = [k for goal in plan.get("goals", []) for k in goal.get("kpis", [])]
        if kpis:
            selected = st.selectbox("Select KPI", [k["id"] for k in kpis], format_func=lambda kid: next(k["label"] for k in kpis if k["id"]==kid), key="batch1_outcome_pick")
            rec = records.get("outcome:" + selected, {})
            with st.form("batch1_outcome_form"):
                actual = st.number_input("Verified quantity", min_value=0.0, value=float(rec.get("actual", 0)), step=1.0)
                evidence = st.text_area("Evidence / Verification notes", value=rec.get("evidence", ""))
                verified = st.checkbox("Independently verified", value=bool(rec.get("verified", False)))
                if st.form_submit_button("Save verified outcome"):
                    if verified and not evidence.strip():
                        st.error("A verified outcome requires evidence notes.")
                    else:
                        store.save("outcome:"+selected, {"actual":actual,"evidence":evidence,"verified":verified,"date":chosen.isoformat()})
                        st.success("Saved privately.")
                        st.rerun()
    else:
        st.info("Unlock private tracking to record verified outcomes.")
    if domain == "D04":
        st.markdown("#### Weight verification (independent from training checkboxes)")
        for qid, deadline, target in [("Q1",date(2027,1,3),91),("Q2",date(2027,4,4),83),("Q3",date(2027,7,4),75)]:
            result = seven_day_qualifies(records, deadline, target)
            st.write(f"{qid}: <= {target} kg by {deadline.isoformat()} · " +
                     ("✅ Verified, 7-day mean " + str(result["average"]) + " kg, ending " + result["end"] if result and "end" in result else
                      "Not verified" + (" (best 7-day mean: " + str(result["best_complete_window_average"]) + " kg)" if result and "best_complete_window_average" in result else "")))
        if access:
            with st.form("batch1_weight"):
                w = st.number_input("Morning weight (kg)", min_value=30.0, max_value=300.0, step=0.1)
                if st.form_submit_button("Save morning weight"):
                    store.save("metric:D04:weight:" + chosen.isoformat(), {"value":w,"unit":"kg","date":chosen.isoformat()})
                    st.success("Saved privately.")
                    st.rerun()
    st.markdown("### 3 · Habit counters / 习惯次数")
    habits = D03_HABITS if domain == "D03" else D04_HABITS if domain == "D04" else []
    if domain == "D05":
        for path in sorted((ROOT / "data/routines/D05").glob("*.json")):
            try:
                routine = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            st.markdown("**"+routine["label"]+"**")
            for step in routine.get("steps", []):
                if not step.get("active", False):
                    with st.expander(step["title"]+" · requires product/frequency review"):
                        st.write(step.get("product", {}).get("instructions",""))
                    continue
                freq = step.get("frequency", {})
                habits.append((step["step_id"],step["title"],freq.get("planned_per_week") or 0,"times"))
                with st.expander("Product details · "+step["title"]):
                    st.write("Product: "+str(step.get("product",{}).get("name") or "Not yet selected"))
                    st.write(step.get("product",{}).get("instructions",""))
    start = week_start(chosen)
    end = start + timedelta(days=6)
    st.caption(f"Selected week: {start} – {end}. Each day has one keyed record per step; a completed check cannot be counted twice.")
    for habit_id, label, planned, unit in habits:
        prefix = f"habit:{domain}:{habit_id}:"
        completed = sum(float(rec.get("value", 0)) for key, rec in records.items()
                        if key.startswith(prefix) and start.isoformat() <= key.rsplit(":",1)[-1] <= end.isoformat())
        if unit == "hours":
            st.write(f"{label}: {completed:g} / {planned:g} {unit} (reference, not hard quota)")
            if access:
                prior = records.get(prefix+chosen.isoformat(),{}).get("value",0)
                val = st.number_input("Hours on "+str(chosen), min_value=0.0, max_value=24.0, value=float(prior), step=0.5, key="h_"+habit_id)
                if st.button("Save hours · "+label, key="save_"+habit_id):
                    store.save(prefix+chosen.isoformat(),{"value":val,"date":chosen.isoformat()})
                    st.rerun()
        else:
            st.write(f"{label}: {completed:g} / {planned:g} {unit}")
            prior = bool(records.get(prefix+chosen.isoformat(),{}).get("value",0))
            if access:
                checked = st.checkbox(label+" · "+str(chosen), value=prior, key="check_"+domain+"_"+habit_id+"_"+chosen.isoformat())
                if checked != prior:
                    store.save(prefix+chosen.isoformat(),{"value":int(checked),"date":chosen.isoformat()})
                    st.rerun()
    if access:
        st.caption("Private database connected. Changes are persisted; do not store personal measurements in public repository files.")
