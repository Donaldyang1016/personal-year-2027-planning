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
def load_plans(data_signature):
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

# Cache invalidation depends on actual JSON file metadata, not solely Python changes.
file_signature = tuple(sorted(
    (p.name, p.stat().st_mtime_ns, p.stat().st_size)
    for p in DATA_DIR.glob('D[0-9][0-9].json')
)) if DATA_DIR.is_dir() else ()
plans, load_errors = load_plans(file_signature)
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

# D01 V4 execution: a monthly deliverable can be auto-satisfied by its
# linked weekly steps OR independently verified ahead of schedule.
weekly_children = {}
for week in weekly_plans:
    for step in week.get('tasks', []):
        parent_id = step.get('monthly_task_id')
        if parent_id:
            weekly_children.setdefault(parent_id, []).append(step)


def task_done(task):
    tid = task['id']
    rec = st.session_state.todo_records[tid]
    if task.get('task_type') == 'verified_deliverable':
        if rec['done']:
            return True
        children = weekly_children.get(tid, [])
        # Skipping a required step does NOT prove a completed deliverable.
        return bool(children) and all(
            st.session_state.todo_records[x['id']]['done']
            and not st.session_state.todo_records[x['id']]['skipped']
            for x in children
        )
    parent_id = task.get('monthly_task_id')
    if parent_id and parent_id in st.session_state.todo_records:
        if st.session_state.todo_records[parent_id]['done']:
            return True  # Verified early: weekly work is satisfied by the outcome.
    return bool(rec['done'])


def todo_progress(tasks):
    included = [t for t in tasks if not st.session_state.todo_records[t['id']]['skipped']]
    completed = sum(bool(task_done(t)) for t in included)
    return completed, len(included)


def verify_deliverable(tid):
    rec = st.session_state.todo_records[tid]
    rec.update({'done': not rec['done'], 'skipped': False,
                'updated_at': datetime.now().isoformat(timespec='seconds')})
    st.session_state.activity_log.insert(0, {
        'task_id': tid, 'date': rec['updated_at'],
        'verified_early': rec['done'], 'type': 'manual_deliverable_verification'
    })
    st.session_state.activity_log = st.session_state.activity_log[:1500]


def render_deliverables(tasks):
    if not tasks:
        st.info('No monthly deliverables for this period.')
        return
    progress_bar(tasks, 'Verified deliverables / 可验收交付')
    for task in tasks:
        tid = task['id']
        rec = st.session_state.todo_records[tid]
        children = weekly_children.get(tid, [])
        done_steps = sum(task_done(c) for c in children)
        completed = task_done(task)
        with st.container(border=True):
            left, right = st.columns([5, 1], vertical_alignment='top')
            with left:
                st.markdown(('✅ ' if completed else '⬜ ') + '**' + task.get('title', tid) + '**')
                st.caption(f"{task.get('priority', 'Normal')} · {task.get('goal_id', '')} · {done_steps}/{len(children)} weekly steps")
                st.write('**验收标准 / Evidence:** ' + str(task.get('acceptance_criteria', task.get('evidence', '—'))))
            with right:
                if rec['done']:
                    st.caption('Verified early / 手工验收')
                    st.button('Undo verify', key='undo_'+tid,
                              on_click=verify_deliverable, args=(tid,))
                elif completed:
                    st.caption('Auto-completed / 周行动已完成')
                else:
                    st.button('✓ Verify now', key='verify_'+tid,
                              on_click=verify_deliverable, args=(tid,),
                              help='Use only when the deliverable already meets its acceptance criteria.')
            if children:
                with st.expander(f"Linked weekly steps / 关联周任务 · {done_steps}/{len(children)}"):
                    for child in children:
                        status = '✅' if task_done(child) else ('⊘' if st.session_state.todo_records[child['id']]['skipped'] else '○')
                        st.markdown(f"{status} {child.get('title', child['id'])}")
    st.caption('Automatic roll-up: all linked applicable weekly steps completed → monthly delivered. Manual Verify enables early completion.')


def execution_stats_for_goal(gid):
    relevant = [t for m in monthly_plans for t in m.get('tasks', [])
                if t.get('goal_id') == gid]
    return todo_progress(relevant) if relevant else (0, 0)



def update_todo(tid, field):
    rec = st.session_state.todo_records[tid]
    new_value = bool(st.session_state[f'{field}_{tid}'])
    rec[field] = new_value
    if new_value:
        opposite = 'skipped' if field == 'done' else 'done'
        rec[opposite] = False
        # A callback runs before widgets are instantiated on this rerun.
        st.session_state[f'{opposite}_{tid}'] = False
    rec['updated_at'] = datetime.now().isoformat(timespec='seconds')
    st.session_state.activity_log.insert(0, {
        'task_id': tid, 'date': rec['updated_at'],
        'done': rec['done'], 'skipped': rec['skipped']
    })
    st.session_state.activity_log = st.session_state.activity_log[:1500]


def progress_bar(tasks, label='Completion / 完成率'):
    done, total = todo_progress(tasks)
    pct = round(100 * done / total) if total else 0
    a, b = st.columns([4, 1], vertical_alignment='center')
    with a:
        st.caption(label)
        st.progress(done / total if total else 0)
    with b:
        st.metric('Completed', f'{done}/{total}')
    return pct


def render_todos(tasks, key_prefix='weekly'):
    """Only concrete steps get checkboxes; parent verification satisfies steps."""
    if not tasks:
        st.info('本周没有需要强制打卡的交付任务 / No required steps this week.')
        return
    progress_bar(tasks, 'Weekly actions / 本周行动')
    for task in tasks:
        tid = task['id']
        rec = st.session_state.todo_records[tid]
        parent_id = task.get('monthly_task_id')
        parent_verified = bool(parent_id and parent_id in st.session_state.todo_records
                               and st.session_state.todo_records[parent_id]['done'])
        if parent_verified:
            st.markdown('✅ **' + task.get('title', tid) + '**')
            st.caption('Already satisfied · Monthly deliverable verified early')
            st.divider()
            continue
        check_key, skip_key = f'done_{tid}', f'skipped_{tid}'
        if check_key not in st.session_state:
            st.session_state[check_key] = bool(rec['done'])
        if skip_key not in st.session_state:
            st.session_state[skip_key] = bool(rec['skipped'])
        left, right = st.columns([5, 1], vertical_alignment='center')
        with left:
            st.checkbox(task.get('title', tid), key=check_key,
                        disabled=bool(rec['skipped']),
                        on_change=update_todo, args=(tid, 'done'))
            st.caption(f"{task.get('priority', 'Normal')} · {task.get('goal_id', '')}")
        with right:
            st.checkbox('N/A', key=skip_key,
                        on_change=update_todo, args=(tid, 'skipped'),
                        help='N/A excludes a step from weekly count, but does not prove monthly delivery.')
        with st.expander('Acceptance / 验收与关联目标'):
            st.write('**This step:** ' + task.get('acceptance_criteria', 'Complete actual work.'))
            if parent_id in todo_by_id:
                parent = todo_by_id[parent_id]
                st.write('**Monthly deliverable:** ' + parent.get('title', parent_id))
                st.write('**Monthly acceptance:** ' + parent.get('acceptance_criteria', parent.get('evidence', '—')))
        st.divider()

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


# ---------------------------------------------------------------------------
# Personal Year 2027 V3 — Planning (rich) and Execution (action-first)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
.block-container{padding-top:1.4rem;max-width:1240px}
[data-testid="stMetric"]{border:1px solid rgba(128,128,128,.18);padding:12px;border-radius:12px}
[data-testid="stVerticalBlock"] > div{scroll-margin-top:1rem}
</style>
""", unsafe_allow_html=True)

DOMAIN_LABELS = {
    'D01': 'Career & Professional Development',
    'D02': 'Immigration & PR', 'D03': 'Learning & Skills',
    'D04': 'Health & Fitness', 'D05': 'Personal Image',
    'D06': 'Personal Finance', 'D07': 'Relationships',
    'D08': 'Social Life', 'D09': 'Travel',
    'D10': 'Interests', 'D11': 'Daily Life',
    'D12': 'Mental Wellbeing'
}

def pretty_domain(did):
    return f"{did} · {by_domain.get(did, {}).get('domain_name') or DOMAIN_LABELS.get(did, did)}"

def active_goals(did):
    return by_domain.get(did, {}).get('goals', [])

def objectives_status(tasks):
    d, n = todo_progress(tasks)
    return f'{d}/{n} completed'

def milestone_title(g):
    return g.get('title_zh') or g.get('title') or g['id']

def plan_vision(plan):
    star = plan.get('north_star', {})
    if isinstance(star, dict):
        if star.get('vision_zh'):
            st.write(star['vision_zh'])
        if star.get('core_outcomes'):
            st.markdown('**Annual outcomes / 年度结果**')
            for item in star['core_outcomes']:
                st.markdown('- ' + str(item))
        if star.get('career_horizon_2030'):
            st.caption('Long-term / 长期方向：' + str(star['career_horizon_2030']))
    elif star:
        st.write(star)

def goal_card(g, quarter=None):
    gid = g['id']
    rec = st.session_state.goal_records[gid]
    heading = milestone_title(g)
    with st.expander(f"{gid} · {heading}  |  {rec['status']}", expanded=False):
        st.caption(f"Priority: {g.get('priority', '—')}  ·  Deadline: {g.get('due', 'TBD')}")
        if quarter:
            st.markdown(f"**{quarter} Milestone / 本季度交付**")
            st.write(g.get('quarterly', {}).get(quarter, 'No milestone defined'))
        else:
            cols = st.columns(3)
            for col, (name, field) in zip(cols, [('MUST · 底线', 'must'), ('TARGET · 目标', 'target'), ('STRETCH · 冲刺', 'stretch')]):
                with col:
                    st.markdown('**' + name + '**')
                    st.write(g.get(field, '—'))
            st.markdown('**Quarterly roadmap / 季度路径**')
            for q, value in g.get('quarterly', {}).items():
                st.markdown(f'**{q}** · {value}')
        if g.get('kpis'):
            st.markdown('**Success metrics / KPI**')
            metrics = []
            for k in g['kpis']:
                metrics.append({
                    'Metric / 指标': k.get('label', k['id']),
                    'Target': k.get('target'),
                    'Actual': st.session_state.kpi_records[k['id']].get('actual'),
                    'Unit': k.get('unit', ''),
                    'Deadline': k.get('deadline', ''),
                    'Level': k.get('level', '')
                })
            st.dataframe(pd.DataFrame(metrics), hide_index=True, use_container_width=True)
        if g.get('plan_b'):
            st.markdown('**Plan B / 备选方案**')
            st.write(g['plan_b'])
        st.progress(rec['progress'] / 100, text=f"Self-reported objective progress: {rec['progress']}%")
        if rec.get('notes'):
            st.caption('Evidence: ' + rec['notes'])

def page_header(kicker, headline, description):
    st.caption(kicker)
    st.title(headline)
    st.write(description)

def month_sort(m):
    return (m.get('month', ''), m.get('id', ''))

def week_sort(w):
    return (w.get('start', ''), w.get('id', ''))

with st.sidebar:
    st.title('🎯 Personal Year 2027')
    st.caption('V3 · Planning + Execution')
    st.markdown('**PLANNING / 战略**')
    st.caption('Annual & Quarterly → detailed goals, milestones, KPIs, Plan B')
    st.markdown('**EXECUTION / 执行**')
    st.caption('Monthly & Weekly → tasks, checkboxes, progress')
    st.divider()
    st.caption('Tracker data is held in this Streamlit session. Export backup regularly.')
    st.download_button(
        '⬇️ Export tracker backup',
        data=json.dumps(export_backup(), ensure_ascii=False, indent=2),
        file_name=f'tracker-backup-{date.today().isoformat()}.json',
        mime='application/json', use_container_width=True
    )
    upload = st.file_uploader('Restore tracker backup', type='json')
    if upload is not None and st.button('Import backup', use_container_width=True):
        try:
            restore_backup(json.load(upload))
            # Synchronize Streamlit widget state with the restored records.
            for tid in todo_by_id:
                st.session_state.pop(f'done_{tid}', None)
                st.session_state.pop(f'skipped_{tid}', None)
            st.success('Backup restored.')
            st.rerun()
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(str(exc))
    if load_errors:
        for err in load_errors:
            st.error('Domain data: ' + err)
    st.caption(f"Loaded domains: {len(plans)} · Months: {len(monthly_plans)} · Weeks: {len(weekly_plans)}")
    if by_domain.get('D01'):
        st.caption('D01 version: ' + str(by_domain['D01'].get('plan_version', 'unknown')))
        st.caption('Timeline: ' + str(monthly_plans[0].get('month')) + ' → ' + str(monthly_plans[-1].get('month')) if monthly_plans else 'No months')

tabs = st.tabs([
    '🏠 Dashboard', '🎯 Annual', '📅 Quarterly',
    '🗓️ Monthly', '✅ Weekly', '📈 Progress'
])

with tabs[0]:
    page_header('OVERVIEW · 全年总览', 'Personal Year 2027',
                'Strategy lives in Annual / Quarterly. Actions live in Monthly / Weekly.')
    complete = sum(st.session_state.goal_records[g['id']]['status'] == 'Completed' for g in goals)
    done, total = todo_progress(list(todo_by_id.values())) if todo_by_id else (0, 0)
    a, b, c, d = st.columns(4)
    a.metric('Life domains', '12')
    b.metric('Imported plans', len(plans))
    c.metric('Annual objectives', len(goals))
    d.metric('Tasks completed', f'{done}/{total}')
    if total:
        st.progress(done / total, text=f'Execution completion: {round(100*done/total)}%')
    st.subheader('Your 12 domains / 领域一览')
    for i in range(0, 12, 3):
        cols = st.columns(3)
        for j, did in enumerate(domain_ids[i:i+3]):
            with cols[j]:
                plan = by_domain.get(did)
                with st.container(border=True):
                    st.markdown('**' + pretty_domain(did) + '**')
                    if plan:
                        st.caption(f"{len(plan.get('goals', []))} annual goals · Plan loaded")
                    else:
                        st.caption('Pending · 尚未导入')
    st.subheader('What matters now / 当前重点')
    if goals:
        for g in goals:
            if g.get('priority') in ('P0', 'P1'):
                st.markdown(f"**{g['id']} · {milestone_title(g)}** — Due {g.get('due', 'TBD')}")
    else:
        st.info('Upload data/domains/D01.json to begin.')

with tabs[1]:
    page_header('PLANNING · 年度规划', 'Annual Goals / 年度目标',
                'Read the detailed goals here. Track daily work in Weekly.')
    did = st.selectbox('Domain / 选择领域', domain_ids,
                       format_func=pretty_domain, key='v3_annual_domain')
    plan = by_domain.get(did)
    if not plan:
        st.info(f'No plan uploaded for {did}. Expected: data/domains/{did}.json')
    else:
        st.caption(str(plan.get('plan_version', 'Annual plan')))
        with st.container(border=True):
            st.markdown('### North Star / 年度愿景')
            plan_vision(plan)
        items = active_goals(did)
        a, b, c = st.columns(3)
        a.metric('Objectives', len(items))
        b.metric('KPIs', sum(len(g.get('kpis', [])) for g in items))
        c.metric('Objectives completed', sum(st.session_state.goal_records[g['id']]['status'] == 'Completed' for g in items))
        strategy = plan.get('annual_strategy', {})
        if strategy:
            with st.container(border=True):
                st.markdown('### Strategic outcomes / 年度战略成果')
                for item in strategy.get('primary_outcomes', []):
                    st.markdown(f"**{item.get('goal_id', '')}** · {item.get('description', '')}")
                st.markdown('**Decision rule / 决策原则**')
                st.write(strategy.get('decision_rule', ''))
                st.caption(strategy.get('success_rule', ''))
        st.markdown('### Execution contribution / 年度执行贡献')
        st.caption('These are verified deliverables, not proof that a real-world outcome or KPI has been achieved.')
        execution_rows = []
        for g in items:
            completed, applicable = execution_stats_for_goal(g['id'])
            execution_rows.append({'Objective': milestone_title(g), 'Delivered': completed,
                                   'Planned': applicable,
                                   'Execution %': round(100*completed/applicable) if applicable else 0})
        st.dataframe(pd.DataFrame(execution_rows), hide_index=True, use_container_width=True)
        st.markdown('### Detailed objectives / 详细年度目标')
        for g in items:
            goal_card(g)
        if plan.get('contingencies'):
            with st.expander('Contingency scenarios / 风险预案'):
                st.dataframe(pd.DataFrame(plan['contingencies']), hide_index=True, use_container_width=True)

with tabs[2]:
    page_header('PLANNING · 季度里程碑', 'Quarterly Goals / 季度目标',
                'Strategic decisions, outcomes and KPI gates — not daily checklists.')
    periods = by_domain.get('D01', {}).get('planning_periods', [])
    quarter_options = [p['id'] for p in periods] if periods else ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
    period_labels = {p['id']: f"{p['id']} · {p['start']} → {p['end']} · {p.get('title', '')}" for p in periods}
    q = st.selectbox('Planning period / 规划阶段', quarter_options,
                     format_func=lambda x: period_labels.get(x, x), key='v3_q')
    filter_domain = st.selectbox('Domain', ['All'] + domain_ids,
                                 format_func=lambda d: 'All imported domains' if d == 'All' else pretty_domain(d), key='v3_q_domain')
    strategic = []
    source_plans = plans if filter_domain == 'All' else [by_domain[filter_domain]] if filter_domain in by_domain else []
    for source_plan in source_plans:
        for quarter_plan in source_plan.get('quarterly_plans', []):
            if quarter_plan.get('quarter') == q:
                strategic.append((source_plan, quarter_plan))
    for source_plan, quarter_plan in strategic:
        st.subheader(f"{source_plan['domain_id']} · {quarter_plan.get('title', q)}")
        with st.container(border=True):
            st.caption(quarter_plan.get('dates', ''))
            st.markdown('**Strategic focus / 战略方向**')
            st.write(quarter_plan.get('strategic_focus', ''))
            st.markdown('**Must-win outcomes / 本季关键成果**')
            for item in quarter_plan.get('must_win', []):
                st.markdown('- ' + str(item))
            st.markdown('**Decision gate / 决策节点**')
            st.write(quarter_plan.get('decision_gate', ''))
            if quarter_plan.get('risk_trigger'):
                st.markdown('**Risk trigger / 风险预案触发条件**')
                st.write(quarter_plan['risk_trigger'])
            linked = [kpis[kid] for kid in quarter_plan.get('kpi_ids', []) if kid in kpis]
            if linked:
                st.markdown('**Priority KPIs / 重点指标**')
                st.dataframe(pd.DataFrame([{
                    'KPI': k.get('label', k['id']),
                    'Target': k.get('target'),
                    'Actual': st.session_state.kpi_records[k['id']].get('actual'),
                    'Deadline': k.get('deadline', '')
                } for k in linked]), hide_index=True, use_container_width=True)
        related_months = [m for m in monthly_plans if m.get('quarter') == q and
                          m.get('id', '').startswith(source_plan['domain_id'] + '-')]
        qtasks = [task for month in related_months for task in month.get('tasks', [])]
        qdone, qtotal = todo_progress(qtasks) if qtasks else (0, 0)
        st.metric('Quarter execution / 当季已验收交付', f'{qdone}/{qtotal}')
        if qtotal:
            st.progress(qdone / qtotal)
        st.caption('Quarter execution is calculated from monthly deliverables; KPI outcomes remain separately verified.')
        st.markdown('**Objective milestones / 各目标季度里程碑**')
        for entry in quarter_plan.get('objective_milestones', []):
            g = goal_by_id.get(entry.get('goal_id'))
            if g:
                goal_card(g, quarter=q)
    if not strategic:
        filtered = [g for g in goals if (filter_domain == 'All' or g['domain'] == filter_domain) and g.get('quarterly', {}).get(q)]
        if not filtered:
            st.info('No quarterly goals available for this selection.')
        else:
            st.caption('Legacy quarterly format / 兼容旧领域数据')
            for g in filtered:
                goal_card(g, quarter=q)

def period_name(pid):
    periods = by_domain.get('D01', {}).get('planning_periods', [])
    item = next((p for p in periods if p.get('id') == pid), None)
    return f"{pid} · {item['start']} – {item['end']}" if item else pid


def month_periods(m):
    return m.get('period_ids') or [m.get('quarter', '')]


def execution_overview(items, unit_label):
    done = applicable = 0
    for item in items:
        a, b = todo_progress(item.get('tasks', []))
        done += a
        applicable += b
    x, y = st.columns(2)
    x.metric(f'{unit_label} plans / 计划', len(items))
    y.metric('Tasks done / 已完成', f'{done}/{applicable}')
    if applicable:
        st.progress(done / applicable, text=f'Completion / 完成率 {round(done / applicable * 100)}%')


with tabs[3]:
    page_header('EXECUTION · 月度交付', 'Monthly Planner / 月度计划',
                'Includes 2026 launch months, 2027 and the January 2028 closeout. Select a period to see its actionable deliverables.')
    months = sorted(monthly_plans, key=month_sort)
    if not months:
        st.error('No monthly plans loaded. Check GitHub JSON and the loaded data version shown below.')
    else:
        period_options = ['All'] + [p['id'] for p in by_domain.get('D01', {}).get('planning_periods', [])]
        period_choice = st.selectbox('Planning period / 五阶段筛选', period_options,
            format_func=lambda x: 'All periods · 2026–2028' if x == 'All' else period_name(x), key='v31_month_period')
        visible = [m for m in months if period_choice == 'All' or period_choice in month_periods(m)]
        execution_overview(visible, 'Monthly')
        current_month = date.today().strftime('%Y-%m')
        idx = next((i for i, m in enumerate(visible) if m.get('month') == current_month), 0)
        selected_month_id = st.selectbox('Month / 选择月份',
            [m['id'] for m in visible], index=idx,
            format_func=lambda mid: next(f"{m['month']} · {m['title']}" for m in visible if m['id'] == mid),
            key='v31_month')
        m = next(item for item in visible if item['id'] == selected_month_id)
        st.caption(f"Selected month: {m['month']} · {', '.join(month_periods(m))}")
        with st.container(border=True):
            st.markdown('### Monthly outcome / 本月成果')
            st.write(m.get('outcome', '—'))
        render_deliverables(m.get('tasks', []))
        if m.get('guidance'):
            with st.expander('Guidance / 非打卡建议'):
                for suggestion in m['guidance']:
                    st.markdown('- ' + str(suggestion))
        st.caption('Monthly delivery and weekly actions are separate checklists. Each has its own progress.')

with tabs[4]:
    page_header('EXECUTION · 每周行动', 'Weekly To-do / 每周任务',
                'Starts November 16, 2026. Use the stage filter and weekly checkboxes.')
    weeks = sorted(weekly_plans, key=week_sort)
    if not weeks:
        st.error('No weekly plans loaded. Check GitHub JSON and the loaded data version shown below.')
    else:
        period_options = ['All'] + [p['id'] for p in by_domain.get('D01', {}).get('planning_periods', [])]
        period_choice = st.selectbox('Planning period / 五阶段筛选', period_options,
            format_func=lambda x: 'All periods · 2026–2028' if x == 'All' else period_name(x), key='v31_week_period')
        visible = [w for w in weeks if period_choice == 'All' or w.get('quarter') == period_choice]
        execution_overview(visible, 'Weekly')
        today_str = date.today().isoformat()
        idx = next((i for i, w in enumerate(visible) if w.get('start', '') <= today_str <= w.get('end', '')), 0)
        week_id = st.selectbox('Week / 选择周', [w['id'] for w in visible], index=idx,
            format_func=lambda wid: next(f"{w['start']} → {w['end']} · {w['title']}" for w in visible if w['id'] == wid),
            key='v31_week')
        w = next(item for item in visible if item['id'] == week_id)
        with st.container(border=True):
            st.markdown(f"### {w.get('title', week_id)}")
            st.caption(f"{w.get('start')} – {w.get('end')} · {w.get('quarter', '')}")
        render_todos(w.get('tasks', []), 'week')
        if w.get('guidance'):
            st.caption('Guidance / 建议：' + w['guidance'])
        st.caption('Checkboxes track execution, not automatic attainment of annual KPIs.')

with tabs[5]:
    page_header('REVIEW · 结果复盘', 'Progress & Evidence / 进度追踪',
                'Execution completion and real objective achievement are tracked separately.')
    if not goals:
        st.info('Upload a domain plan to start tracking.')
    else:
        st.subheader('Execution / 2026–2028 执行完成率')
        st.caption('Weekly steps automatically roll up to monthly deliverables. Verified early deliverables count immediately. Annual KPI results are NOT inferred from execution checkboxes.')
        period_options = ['All'] + [p['id'] for p in by_domain.get('D01', {}).get('planning_periods', [])]
        review_period = st.selectbox('Review period / 进度阶段', period_options,
            format_func=lambda x: 'All periods · Full personal year' if x == 'All' else period_name(x), key='v31_progress_period')
        for heading, items, filter_function, name_key in [
            ('Monthly deliverables / 月度成果', sorted(monthly_plans, key=month_sort),
             lambda item: review_period == 'All' or review_period in month_periods(item), 'month'),
            ('Weekly actions / 每周行动', sorted(weekly_plans, key=week_sort),
             lambda item: review_period == 'All' or item.get('quarter') == review_period, 'start'),
        ]:
            selected_items = [item for item in items if filter_function(item)]
            st.markdown('**' + heading + '**')
            rows = []
            for item in selected_items:
                done, total = todo_progress(item.get('tasks', []))
                rows.append({'Period': item.get('quarter'), 'Date': item.get(name_key),
                             'Plan': item.get('title'), 'Done': done, 'Applicable': total,
                             'Completion %': round(100 * done / total) if total else 0})
            if rows:
                execution_overview(selected_items, 'Monthly' if name_key == 'month' else 'Weekly')
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            else:
                st.info('No execution tasks for this period.')
        st.subheader('Annual objective review / 年度目标评估')
        gid = st.selectbox('Objective', list(goal_by_id),
            format_func=lambda x: f"{x} · {milestone_title(goal_by_id[x])}", key='v3_review_goal')
        rec = st.session_state.goal_records[gid]
        with st.form('v3_goal_form'):
            status = st.selectbox('Status', STATUSES, index=STATUSES.index(rec['status']))
            progress = st.slider('Self-reported progress (%)', 0, 100, int(rec['progress']))
            notes = st.text_area('Evidence / 证据备注', value=rec['notes'])
            if st.form_submit_button('Save objective assessment'):
                stamp = datetime.now().isoformat(timespec='seconds')
                st.session_state.goal_records[gid] = {
                    'status': status, 'progress': progress,
                    'notes': notes, 'updated_at': stamp
                }
                st.session_state.activity_log.insert(0, {'goal_id': gid, 'date': stamp, 'status': status, 'progress': progress})
                st.success('Saved in this session. Export backup when finished.')
        kpi_items = goal_by_id[gid].get('kpis', [])
        if kpi_items:
            st.subheader('KPI actual / 实际指标')
            kid = st.selectbox('Metric', [k['id'] for k in kpi_items],
                format_func=lambda x: f"{x} · {kpis[x].get('label', '')}", key='v3_kpi')
            item = kpis[kid]
            previous = st.session_state.kpi_records[kid]
            st.caption(f"Target: {item.get('target', '—')} {item.get('unit', '')} · Deadline: {item.get('deadline', '')}")
            with st.form('v3_kpi_form'):
                actual = st.number_input('Actual value', value=float(previous['actual'] or 0), step=1.0)
                evidence = st.text_area('Evidence / Notes', value=previous['notes'])
                if st.form_submit_button('Save KPI'):
                    stamp = datetime.now().isoformat(timespec='seconds')
                    st.session_state.kpi_records[kid] = {'actual': actual, 'notes': evidence, 'updated_at': stamp}
                    st.session_state.activity_log.insert(0, {'kpi_id': kid, 'date': stamp, 'actual': actual})
                    st.success('KPI saved for this session.')
        with st.expander('All objective status / 全部目标'):
            st.dataframe(pd.DataFrame([
                {'Domain': g['domain'], 'Objective': milestone_title(g),
                 'Status': st.session_state.goal_records[g['id']]['status'],
                 'Progress %': st.session_state.goal_records[g['id']]['progress']}
                for g in goals
            ]), hide_index=True, use_container_width=True)
        if st.session_state.activity_log:
            with st.expander('Recent activity / 最近更新'):
                st.dataframe(pd.DataFrame(st.session_state.activity_log[:25]), hide_index=True, use_container_width=True)
