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

if 'goal_records' not in st.session_state:
    st.session_state.goal_records = {}
if 'kpi_records' not in st.session_state:
    st.session_state.kpi_records = {}
if 'activity_log' not in st.session_state:
    st.session_state.activity_log = []
for g in goals:
    st.session_state.goal_records.setdefault(g['id'], {'status': 'Not started', 'progress': 0, 'notes': '', 'updated_at': ''})
for kid in kpis:
    st.session_state.kpi_records.setdefault(kid, {'actual': None, 'notes': '', 'updated_at': ''})

def export_backup():
    return {'schema_version': 2, 'exported_at': datetime.now().isoformat(timespec='seconds'),
            'records': {k: v for k,v in st.session_state.goal_records.items() if k in goal_by_id},
            'kpi_records': {k: v for k,v in st.session_state.kpi_records.items() if k in kpis},
            'activity': st.session_state.activity_log[:1500]}

def restore_backup(data):
    if not isinstance(data, dict) or data.get('schema_version') not in (1,2):
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
    cols[3].metric('KPI targets', len(kpis))

    st.subheader('12 Life Domains')

    rows = [
        {
            'Domain': did,
            'Name': domain_name(did),
            'Status': by_domain.get(did, {}).get('status', 'Not imported'),
            'Objectives': len(by_domain.get(did, {}).get('goals', []))
        }
        for did in domain_ids
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    if goals:
        st.subheader('Highlighted Objectives')
        for g in goals[:4]:
            render_goal(g, details=False)


# ANNUAL PAGE
with tabs[1]:
    st.header('Annual Goals')

    selected_domain = st.selectbox(
        'Life Domain',
        domain_ids,
        format_func=lambda did: f'{did} - {domain_name(did)}'
    )

    plan = by_domain.get(selected_domain)

    if plan is None:
        st.info(f'No plan uploaded for {selected_domain}.')
    else:
        st.caption(plan.get('plan_version', 'Draft'))

        if plan.get('north_star'):
            st.subheader('Annual Vision')
            vision = plan['north_star']
            if isinstance(vision, dict):
                st.write(vision.get('vision_zh', ''))
                for outcome in vision.get('core_outcomes', []):
                    st.write('- ' + outcome)
            else:
                st.write(vision)

        for g in plan.get('goals', []):
            render_goal(g)

        if plan.get('contingencies'):
            st.subheader('Plan B / Contingencies')
            st.dataframe(
                pd.DataFrame(plan['contingencies']),
                hide_index=True,
                use_container_width=True
            )


# QUARTERLY PAGE
with tabs[2]:
    st.header('Quarterly Milestones')

    quarter = st.selectbox(
        'Select Quarter',
        ['Q1', 'Q2', 'Q3', 'Q4']
    )

    selected_domain = st.selectbox(
        'Select Domain',
        ['All'] + domain_ids
    )

    filtered = [
        g for g in goals
        if selected_domain == 'All'
        or g['domain'] == selected_domain
    ]

    rows = [
        {
            'Domain': g['domain'],
            'Goal': g['id'],
            'Objective': g.get('title_zh', g.get('title', '')),
            'Milestone': g.get('quarterly', {}).get(quarter, ''),
            'Status': st.session_state.goal_records[g['id']]['status']
        }
        for g in filtered
    ]

    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info('No quarterly milestones available.')


# MONTHLY PAGE
with tabs[3]:
    st.header('Monthly Goals')
    st.info(
        'Monthly plans will be added after annual '
        'and quarterly planning is completed.'
    )


# WEEKLY PAGE
with tabs[4]:
    st.header('Weekly Goals')
    st.info(
        'Weekly plans will be added after monthly '
        'planning is completed.'
    )


# TRACKER PAGE
with tabs[5]:
    st.header('Progress Tracker')

    if not goals:
        st.warning('No domain data loaded.')

    else:
        selected = st.selectbox(
            'Select Objective',
            list(goal_by_id),
            format_func=lambda gid: (
                f"{gid} - "
                f"{goal_by_id[gid].get('title_zh', '')}"
            )
        )

        rec = st.session_state.goal_records[selected]

        with st.form('goal_tracker'):
            status = st.selectbox(
                'Status',
                STATUSES,
                index=STATUSES.index(rec['status'])
            )

            progress = st.slider(
                'Progress (%)',
                0,
                100,
                int(rec['progress'])
            )

            notes = st.text_area(
                'Notes / Evidence',
                value=rec['notes']
            )

            if st.form_submit_button('Save Goal Progress'):
                stamp = datetime.now().isoformat(timespec='seconds')

                st.session_state.goal_records[selected] = {
                    'status': status,
                    'progress': progress,
                    'notes': notes,
                    'updated_at': stamp
                }

                st.success('Progress saved in this session.')

        target_goal = goal_by_id[selected]

        if target_goal.get('kpis'):
            st.subheader('KPI Tracking')

            kid = st.selectbox(
                'Choose KPI',
                [k['id'] for k in target_goal['kpis']],
                format_func=lambda x: (
                    f"{x} - {kpis[x]['label']}"
                )
            )

            kpi = kpis[kid]
            old = st.session_state.kpi_records[kid]

            st.caption(
                f"Target: {kpi.get('target')} "
                f"{kpi.get('unit', '')} | "
                f"Deadline: {kpi.get('deadline', '')}"
            )

            with st.form('kpi_tracker'):
                actual = st.number_input(
                    'Actual Value',
                    value=float(old['actual'] or 0),
                    step=1.0
                )

                evidence = st.text_area(
                    'KPI Evidence',
                    value=old['notes']
                )

                if st.form_submit_button('Save KPI'):
                    stamp = datetime.now().isoformat(timespec='seconds')

                    st.session_state.kpi_records[kid] = {
                        'actual': actual,
                        'notes': evidence,
                        'updated_at': stamp
                    }

                    st.success('KPI saved in this session.')

        st.subheader('All Goal Progress')

        st.dataframe(
            pd.DataFrame([
                {
                    'Domain': g['domain'],
                    'Goal': g['id'],
                    'Status': st.session_state.goal_records[g['id']]['status'],
                    'Progress': st.session_state.goal_records[g['id']]['progress']
                }
                for g in goals
            ]),
            hide_index=True,
            use_container_width=True
        )
