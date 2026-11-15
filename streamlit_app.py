"""Personal Year 2027 — modular goals engine. Add data/domains/DNN.json without code changes."""
import json
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Personal Year 2027', page_icon='🎯', layout='wide')
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data' / 'domains'
STATUSES = ['Not started', 'In progress', 'At risk', 'Completed', 'Paused']

@st.cache_data(show_spinner=False)
def load_plans():
    plans, errors = [], []
    paths = sorted(DATA_DIR.glob('D[0-9][0-9].json')) if DATA_DIR.is_dir() else []
    if not paths and (ROOT / 'data' / 'goals.json').exists():
        # Compatibility with starter repositories. Modular files take precedence once uploaded.
        raw = json.loads((ROOT / 'data' / 'goals.json').read_text(encoding='utf-8'))
        for d in raw.get('domains', []):
            items = [g for g in raw.get('goals', []) if g.get('domain') == d['id']]
            if items:
                plans.append({'domain_id': d['id'], 'domain_name': d['name'], 'status': d.get('status', 'Draft'), 'goals': items})
        return plans, errors
    seen_goals, seen_kpis = set(), set()
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            domain = path.stem
            if data.get('domain_id') != domain:
                raise ValueError(f'domain_id must match filename: {domain}')
            if not isinstance(data.get('goals'), list):
                raise ValueError('goals must be an array')
            for goal in data['goals']:
                gid = goal['id']
                if goal.get('domain', domain) != domain or not gid.startswith(domain + '-'):
                    raise ValueError(f'Invalid goal ID/domain: {gid}')
                if gid in seen_goals:
                    raise ValueError(f'Duplicate goal ID: {gid}')
                seen_goals.add(gid)
                for kpi in goal.get('kpis', []):
                    kid = kpi['id']
                    if kid in seen_kpis:
                        raise ValueError(f'Duplicate KPI ID: {kid}')
                    seen_kpis.add(kid)
            plans.append(data)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f'{path.name}: {exc}')
    return plans, errors

plans, load_errors = load_plans()
by_domain = {p['domain_id']: p for p in plans}
domain_ids = [f'D{i:02d}' for i in range(1, 13)]
goals = [g for p in plans for g in p.get('goals', [])]
goal_by_id = {g['id']: g for g in goals}
kpis = {k['id']: k for g in goals for k in g.get('kpis', [])}
monthly_plans = [m for p in plans for m in p.get('monthly_plans', [])]
weekly_plans = [w for p in plans for w in p.get('weekly_plans', [])]
todo_by_id = {t['id']: t for plan in monthly_plans + weekly_plans for t in plan.get('tasks', [])}


if 'goal_records' not in st.session_state:
    st.session_state.goal_records = {}
if 'kpi_records' not in st.session_state:
    st.session_state.kpi_records = {}
if 'todo_records' not in st.session_state:
    st.session_state.todo_records = {}
if 'activity_log' not in st.session_state:
    st.session_state.activity_log = []
for g in goals:
    st.session_state.goal_records.setdefault(g['id'], {'status': 'Not started', 'progress': 0, 'notes': '', 'updated_at': ''})
for kid in kpis:
    st.session_state.kpi_records.setdefault(kid, {'actual': None, 'notes': '', 'updated_at': ''})
for tid in todo_by_id:
    st.session_state.todo_records.setdefault(tid, {'done': False, 'skipped': False, 'updated_at': ''})

def todo_progress(tasks):
    # Skipped conditional tasks are excluded from the completion denominator.
    included = [t for t in tasks if not st.session_state.todo_records[t['id']]['skipped']]
    completed = sum(bool(st.session_state.todo_records[t['id']]['done']) for t in included)
    return completed, len(included)

def render_todos(tasks, key_prefix):
    if not tasks:
        st.info('暂无任务 / No tasks yet')
        return
    completed, total = todo_progress(tasks)
    st.progress(completed / total if total else 1.0, text=f'{completed}/{total} completed · {round(completed / total * 100) if total else 100}%')
    for task in tasks:
        tid = task['id']
        record = st.session_state.todo_records[tid]
        col_a, col_b = st.columns([0.83, 0.17], vertical_alignment='center')
        with col_a:
            marked = st.checkbox(task['title'], value=record['done'], key=f'{key_prefix}_done_{tid}', disabled=record['skipped'])
        with col_b:
            skipped = st.checkbox('Skip / N/A', value=record['skipped'], key=f'{key_prefix}_skip_{tid}', help='Exclude unavailable or conditional tasks')
        if marked != record['done'] or skipped != record['skipped']:
            record.update({'done': marked if not skipped else False, 'skipped': skipped, 'updated_at':datetime.now().isoformat(timespec='seconds')})
            st.session_state.activity_log.insert(0,{'task_id':tid,'date':record['updated_at'],'done':record['done'],'skipped':skipped})
            st.rerun()
        st.caption(f"{tid}  ·  {task.get('goal_id','')}  ·  {task.get('priority','')}")


def export_backup():
    return {'schema_version': 3, 'exported_at': datetime.now().isoformat(timespec='seconds'),
            'records': {k: v for k,v in st.session_state.goal_records.items() if k in goal_by_id},
            'kpi_records': {k: v for k,v in st.session_state.kpi_records.items() if k in kpis},
            'todo_records': {k:v for k,v in st.session_state.todo_records.items() if k in todo_by_id},
            'activity': st.session_state.activity_log[:1500]}

def restore_backup(data):
    if not isinstance(data, dict) or data.get('schema_version') not in (1,2,3):
        raise ValueError('Unsupported tracker backup version')
    recs = data.get('records', {})
    if not isinstance(recs, dict):
        raise ValueError('Invalid goal records')
    for gid, rec in recs.items():
        if gid not in goal_by_id or not isinstance(rec, dict):
            continue
        status = rec.get('status', 'Not started')
        progress = rec.get('progress', 0)
        if status not in STATUSES or not isinstance(progress, int) or not 0 <= progress <= 100:
            continue
        st.session_state.goal_records[gid] = {'status': status, 'progress': progress,
              'notes': str(rec.get('notes',''))[:10000], 'updated_at': str(rec.get('updated_at',''))[:40]}
    kr = data.get('kpi_records', {})
    if isinstance(kr, dict):
        for kid, rec in kr.items():
            if kid in kpis and isinstance(rec, dict):
                actual = rec.get('actual')
                if actual is None or (isinstance(actual, (int,float)) and not isinstance(actual,bool)):
                    st.session_state.kpi_records[kid] = {'actual': actual, 'notes': str(rec.get('notes',''))[:10000],
                                                          'updated_at': str(rec.get('updated_at',''))[:40]}
    todos = data.get('todo_records', {})
    if isinstance(todos, dict):
        for tid, rec in todos.items():
            if tid in todo_by_id and isinstance(rec, dict):
                st.session_state.todo_records[tid] = {
                    'done': bool(rec.get('done', False)) and not bool(rec.get('skipped', False)),
                    'skipped': bool(rec.get('skipped', False)),
                    'updated_at': str(rec.get('updated_at', ''))[:40]}
    if isinstance(data.get('activity'), list):
        st.session_state.activity_log = [a for a in data['activity'] if isinstance(a,dict)][:1500]

def domain_name(did):
    return by_domain.get(did, {}).get('domain_name', 'Pending annual plan')

def render_goal(g, details=True):
    rec = st.session_state.goal_records[g['id']]
    heading = g.get('title_zh') or g.get('title', g['id'])
    with st.expander(f"{g['id']} · {heading}  |  {rec['status']}"):
        st.caption(f"{g.get('section', '')}  ·  {g.get('priority','')}  ·  Due: {g.get('due','TBD')}")
        for label in ('must','target','stretch'):
            st.markdown(f"**{label.title()}** · {g.get(label, 'Not specified')}")
        if details:
            q = g.get('quarterly', {})
            if q:
                st.markdown('**Quarterly milestones**')
                st.dataframe(pd.DataFrame([{'Quarter': key, 'Milestone': val} for key,val in q.items()]), hide_index=True, use_container_width=True)
            if g.get('kpis'):
                st.markdown('**Quantitative KPI targets**')
                rows = []
                for k in g['kpis']:
                    val = st.session_state.kpi_records[k['id']]['actual']
                    rows.append({'KPI': k['label'], 'Target': k.get('target'), 'Unit': k.get('unit',''),
                                 'Actual': val, 'Level': k.get('level',''), 'Deadline': k.get('deadline',''),
                                 'Condition': k.get('condition','Always')})
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            if g.get('dependencies'):
                st.markdown('**Dependencies:** ' + ' · '.join(g['dependencies']))
            if g.get('plan_b'):
                st.markdown('**Plan B:** ' + str(g['plan_b']))
        st.progress(rec['progress'], text=f"Self-reported progress: {rec['progress']}%")
        if rec['notes']:
            st.caption('Latest note: ' + rec['notes'])

st.markdown('''<style>.block-container{padding-top:1.5rem;max-width:1300px}
[data-testid="stMetric"]{border:1px solid rgba(128,128,128,.2);padding:12px;border-radius:12px}</style>''', unsafe_allow_html=True)
with st.sidebar:
    st.title('🎯 Personal Year 2027')
    st.caption('Modular Dashboard · Domain files auto-discovered')
    st.info('Goal definitions come from GitHub JSON files. Tracker edits remain in this browser session until exported.')
    st.download_button('⬇️ Export tracker backup', data=json.dumps(export_backup(), ensure_ascii=False, indent=2),
                       file_name=f'tracker-backup-{date.today().isoformat()}.json', mime='application/json', use_container_width=True)
    upload = st.file_uploader('Restore tracker backup', type='json')
    if upload and st.button('Import backup', use_container_width=True):
        try:
            restore_backup(json.load(upload))
            st.success('Backup restored')
            st.rerun()
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(str(exc))
    if load_errors:
        for err in load_errors:
            st.error('Domain data: ' + err)

st.title('Personal Year 2027')
st.caption('Annual vision → Quarterly milestones → Monthly goals → Weekly action → Tracker')
tabs = st.tabs(['🏠 Home','🎯 Annual','📅 Quarterly','🗓️ Monthly','✅ Weekly','📈 Tracker'])

with tabs[0]:
    completed = sum(st.session_state.goal_records[g['id']]['status'] == 'Completed' for g in goals)
    cols = st.columns(4)
    cols[0].metric('Life domains', 12)
    cols[1].metric('Imported domains', len(plans))
    cols[2].metric('Annual objectives', len(goals))
    cols[3].metric('Completed objectives', completed)
    if todo_by_id:
        done, total = todo_progress(list(todo_by_id.values()))
        st.metric('Checklist tasks completed / 待办完成', f'{done} / {total}')
        st.progress(done / total if total else 1.0)
    st.subheader('12 life domains')
    rows = [{'Domain': did, 'Name': domain_name(did),
             'Plan status': by_domain.get(did,{}).get('status','Not imported'),
             'Objectives': len(by_domain.get(did,{}).get('goals',[]))} for did in domain_ids]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if goals:
        st.subheader('Highlighted objectives')
        for g in goals[:4]:
            render_goal(g, details=False)

with tabs[1]:
    st.header('Annual goals')
    selected_domain = st.selectbox('Life domain', domain_ids, format_func=lambda did: f'{did} · {domain_name(did)}', key='annual_domain')
    plan = by_domain.get(selected_domain)
    if plan is None:
        st.info(f'No approved plan uploaded yet. Add data/domains/{selected_domain}.json on GitHub.')
    else:
        st.caption(f"{plan.get('plan_version','Draft')} · {plan.get('status','')}")
        if plan.get('north_star'):
            st.markdown('**Annual vision / North Star**')
            st.write(plan['north_star'])
        for g in plan.get('goals',[]):
            render_goal(g)
        if plan.get('contingencies'):
            st.subheader('Contingencies')
            st.dataframe(pd.DataFrame(plan['contingencies']), hide_index=True, use_container_width=True)

with tabs[2]:
    st.header('Quarterly milestones')
    quarter = st.selectbox('Quarter', ['Q1','Q2','Q3','Q4'])
    filt = st.selectbox('Domain', ['All'] + domain_ids, format_func=lambda d: d if d=='All' else f'{d} · {domain_name(d)}')
    filtered = [g for g in goals if filt=='All' or g['domain']==filt]
    rows = [{'Domain': g['domain'], 'Goal': g['id'], 'Objective': g.get('title_zh') or g.get('title',''),
             'Milestone': g.get('quarterly',{}).get(quarter, 'Not defined'),
             'Status': st.session_state.goal_records[g['id']]['status']} for g in filtered]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info('No milestones imported for this domain.')

with tabs[3]:
    st.header('Monthly Goals · 月度计划')
    if not monthly_plans:
        st.info('请先在 data/domains/DNN.json 上传 monthly_plans。')
    else:
        choices = [m['id'] for m in monthly_plans]
        cur_month = f'2027-{date.today().month:02d}' if date.today().year == 2027 else '2027-01'
        default = next((i for i,m in enumerate(monthly_plans) if m.get('month') == cur_month), 0)
        selected = st.selectbox('Select month / 选择月份', choices, index=default,
            format_func=lambda key: next(f"{m['month']} · {m['title']}" for m in monthly_plans if m['id']==key))
        month = next(m for m in monthly_plans if m['id'] == selected)
        st.subheader(month['title'])
        st.write('**Monthly outcome / 月度关键成果：** ' + month.get('outcome',''))
        st.caption('Check off tasks as completed; Skip / N/A excludes inapplicable tasks from denominator.')
        render_todos(month['tasks'], 'monthly')
        st.caption('Monthly and weekly checklists are separate views; completing a weekly task does not auto-complete its parent month task.')

with tabs[4]:
    st.header('Weekly Goals · 每周 To-do')
    if not weekly_plans:
        st.info('请先在 data/domains/DNN.json 上传 weekly_plans。')
    else:
        today = date.today().isoformat()
        default = next((i for i,w in enumerate(weekly_plans) if w['start']<=today<=w['end']), 0)
        selected = st.selectbox('Select week / 选择周', [w['id'] for w in weekly_plans], index=default,
            format_func=lambda key: next(f"{w['start']} → {w['end']} · {w['title']}" for w in weekly_plans if w['id']==key))
        week = next(w for w in weekly_plans if w['id']==selected)
        st.subheader(week['title'])
        st.caption(f"Week dates: {week['start']} – {week['end']}")
        render_todos(week['tasks'], 'weekly')
        st.caption('To-do changes live in session memory. Export the tracker backup before leaving.')

with tabs[5]:
    st.header('Progress tracker')
    if not goals:
        st.info('Upload at least one domain plan first.')
    else:
        st.caption('Goal progress is a self-assessment; KPI actual values are separate. Export a backup after edits.')
        selected = st.selectbox('Objective', list(goal_by_id), format_func=lambda gid: f'{gid} · {goal_by_id[gid].get("title_zh") or goal_by_id[gid].get("title","")}')
        rec = st.session_state.goal_records[selected]
        with st.form('edit_goal'):
            status = st.selectbox('Status', STATUSES, index=STATUSES.index(rec['status']))
            progress = st.slider('Self-reported progress (%)', 0, 100, int(rec['progress']))
            notes = st.text_area('Evidence / notes', value=rec['notes'])
            if st.form_submit_button('Save objective progress'):
                stamp = datetime.now().isoformat(timespec='seconds')
                st.session_state.goal_records[selected] = {'status': status,'progress':progress,'notes':notes,'updated_at':stamp}
                st.session_state.activity_log.insert(0, {'goal_id':selected,'date':stamp,'status':status,'progress':progress})
                st.success('Saved to current session. Export backup to keep it.')
        target_goal = goal_by_id[selected]
        if target_goal.get('kpis'):
            st.subheader('Numeric KPI tracking')
            selected_kpi = st.selectbox('KPI', [k['id'] for k in target_goal['kpis']],
                                        format_func=lambda kid: f'{kid} · {kpis[kid]["label"]}')
            kpi = kpis[selected_kpi]
            old_record = st.session_state.kpi_records[selected_kpi]
            st.caption(f"Target: {kpi.get('target')} {kpi.get('unit','')} | Deadline: {kpi.get('deadline','')} | Condition: {kpi.get('condition','Always')}")
            with st.form('edit_kpi'):
                numeric = st.number_input('Actual value', value=float(old_record['actual'] or 0), step=1.0)
                evidence = st.text_area('KPI evidence / notes', value=old_record['notes'])
                if st.form_submit_button('Save KPI actual'):
                    stamp = datetime.now().isoformat(timespec='seconds')
                    st.session_state.kpi_records[selected_kpi] = {'actual':numeric,'notes':evidence,'updated_at':stamp}
                    st.session_state.activity_log.insert(0, {'kpi_id':selected_kpi,'actual':numeric,'date':stamp})
                    st.success('KPI saved to current session. Export backup to keep it.')
        st.subheader('Checklist overview · Todo completion')
        rows = []
        for m in monthly_plans:
            c, n = todo_progress(m['tasks'])
            rows.append({'Month': m.get('month'), 'Done': c, 'Applicable': n, 'Completion (%)': round(100*c/n) if n else 100})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.subheader('All objectives')
        st.dataframe(pd.DataFrame([{'Domain':g['domain'], 'Goal':g['id'],
                   'Status':st.session_state.goal_records[g['id']]['status'],
                   'Progress (%)':st.session_state.goal_records[g['id']]['progress']} for g in goals]),
                   hide_index=True, use_container_width=True)
        if st.session_state.activity_log:
            st.subheader('Recent activity')
            st.dataframe(pd.DataFrame(st.session_state.activity_log[:20]), hide_index=True, use_container_width=True)
