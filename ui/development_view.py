"""Development planning views: drilling schedule, scenario comparison and well-count study."""
from __future__ import annotations
import pandas as pd
from network.development_v26 import DevelopmentTask, DevelopmentPlan, compile_plan, run_development_plan
from network.forecast import run_forecast
from network.prognosis import forecast_kpis, run_scenarios, well_count_study


def _step_solver(st):
    """Optimiser step solver from the shared compute settings (None = plain / pro-rata solve)."""
    try:
        from network.solve_options import make_step_solver
        return make_step_solver(st.session_state.get('compute'))
    except Exception: return None


def _workers(st):
    try: return max(1, int((st.session_state.get('compute') or {}).get('workers', 1)))
    except (TypeError, ValueError): return 1
from ui import charts
from ui.run_button import start_run
from ui.graph_contract import graph_hash
from ui.results_browser import render_results_browser
from ui.forecast_view import kpi_row, profile_charts, fmt, DEFAULT_START
from ui.widgets import clean_num, clean_text
from ui.schedule_builder import render_event_builder, events_to_forecast

WELL_KINDS = ('well', 'water_injector', 'gas_injector')


# --------------------------------------------------------------------------- schedule
def _default_schedule(nodes):
    rows = []; order = 1
    for kind in WELL_KINDS:
        for n in nodes:
            if n.get('kind') != kind: continue
            rows.append({'Include': True, 'Order': order, 'ID': n['id'], 'Well': n.get('name', n['id']),
                         'Type': 'Producer' if kind == 'well' else 'Injector', 'Drill + complete [days]': 60 if kind == 'well' else 45,
                         'Not before (YYYY-MM-DD)': ''})
            order += 1
    return pd.DataFrame(rows)


def render_schedule(st, nodes, edges):
    st.subheader('Development schedule')
    st.caption('Wells come on stream when their rig slot finishes. Rigs work through the list in order; the network and tanks are re-solved through time with each well added.')
    base = _default_schedule(nodes)
    if base.empty:
        st.info('Add wells or injectors to the network to plan their drilling sequence.'); return
    sig = '|'.join(base['ID'])
    if st.session_state.get('sched_sig') != sig:
        st.session_state.sched_sig = sig; st.session_state.sched_df = base
    with st.container(border=True):
        a, b, c, d = st.columns(4)
        start = a.date_input('Drilling start', value=DEFAULT_START, key='sch_start').isoformat()
        rigs = b.number_input('Rigs', 1, 10, 1, 1, key='sch_rigs')
        years = c.number_input('Horizon [years]', 1.0, 50.0, 15.0, 1.0, key='sch_years')
        step = d.selectbox('Report step [days]', [30, 60, 90], index=0, key='sch_step')
        df = st.data_editor(st.session_state.sched_df, hide_index=True, use_container_width=True, key='sched_editor_' + sig,
                            disabled=['ID', 'Well', 'Type'],
                            column_config={'Include': st.column_config.CheckboxColumn(help='Untick to leave the well out of the plan (never drilled)'),
                                           'Order': st.column_config.NumberColumn(min_value=1, step=1, help='Drilling sequence'),
                                           'Drill + complete [days]': st.column_config.NumberColumn(min_value=0, step=5)})
        with st.expander('Operational events (optional): shut-ins, rate limits, debottlenecking ...'):
            st.caption('Added on top of the drilling plan; shared with the Production forecast and Scenarios tabs.')
            sched_events = render_event_builder(st, nodes, edges, None, st.session_state.get('unit_profile', 'norwegian_si'), key_prefix='evb_sch', start_date=start)
        e, f = st.columns(2)
        compare = e.toggle('Compare with all wells on stream at start', value=True, key='sch_cmp')
        caps = f.toggle('Honour facility capacities', value=True, key='sch_caps')
        rb = start_run(st, '▶ Run development plan', key='sch_run', type='primary', model_hash=graph_hash(nodes, edges))
    if rb:
        try:
            rows = sorted([r for r in df.to_dict('records') if bool(r.get('Include'))], key=lambda r: clean_num(r.get('Order'), 999))
            tasks = []
            for i, r in enumerate(rows):
                nb = clean_text(r.get('Not before (YYYY-MM-DD)'))
                nb = pd.Timestamp(nb).date().isoformat() if nb else start
                tasks.append(DevelopmentTask(f"T{i+1}", f"Drill {r['Well']}", 'drill_well', str(r['ID']), nb, int(clean_num(r.get('Drill + complete [days]'), 60)), (), f"RIG-{(i % int(rigs)) + 1}"))
            excluded = [r for r in df.to_dict('records') if not bool(r.get('Include'))]
            ns = [dict(n, params={**(n.get('params') or {}), 'available': False}) if any(n['id'] == r['ID'] for r in excluded) else n for n in nodes]
            user_events = events_to_forecast(sched_events)
            share = 0.5 if compare else 1.0
            def _prog(offset, label):
                return lambda ev: rb.progress(offset + share * ev['step'] / max(ev['n_steps'], 1), f"{label}: {ev['stage']}") and None
            if True:
                # forecast args: nodes, edges, start, years, step, events, depletion
                res = run_development_plan(ns, edges, DevelopmentPlan('Development plan', start, float(years), int(step), tasks),
                                           forecast_runner=lambda nn, ee, d0, yr, st_, evs, dep, *a: run_forecast(nn, ee, d0, yr, st_, [*(evs or []), *user_events], dep, *a, enforce_constraints=bool(caps), step_solver=_step_solver(st), progress=_prog(0.0, 'Scheduled plan')))
                st.session_state.sched_result = res
                st.session_state.sched_base = run_forecast(ns, edges, start, float(years), int(step), user_events or None, None, enforce_constraints=bool(caps), step_solver=_step_solver(st), progress=_prog(0.5, 'All wells at start')) if compare else None
        except Exception as exc:
            rb.fail(f'Development plan failed: {exc}')
        rb.finish()
    res = st.session_state.get('sched_result')
    if not res:
        st.info('Adjust the drilling order and press **Run development plan**.'); return
    sch = pd.DataFrame(res['development_plan']['schedule'])
    if not sch.empty:
        sch = sch.assign(finish=[f if f > s0 else (pd.Timestamp(s0) + pd.Timedelta(days=1)).date().isoformat() for s0, f in zip(sch['start'], sch['finish'])])
        st.plotly_chart(charts.gantt(sch, 'Drilling schedule'), use_container_width=True, key='sch_gantt')
    fc = res['forecast']; k = forecast_kpis(fc)
    st.markdown(f"**First oil:** {k.get('first_oil') or '—'}")
    kpi_row(st, k)
    fdf = pd.DataFrame(fc['field'])
    comp = fdf[['Date', 'Oil [m3/d]']].rename(columns={'Oil [m3/d]': 'Scheduled'})
    base = st.session_state.get('sched_base')
    cols = ['Scheduled']
    if base:
        comp['All wells at start'] = pd.DataFrame(base['field'])['Oil [m3/d]'].values[:len(comp)]
        cols.append('All wells at start')
        kb = forecast_kpis(base)
        loss = kb.get('cum_oil_sm3', 0) - k.get('cum_oil_sm3', 0)
        st.caption(f"Phasing the wells defers {fmt(loss, 'MSm³', 1e6, 2)} of oil over the horizon compared with having every well on stream at start.")
    a, b = st.columns(2)
    a.plotly_chart(charts.lines(comp, 'Date', cols, 'Oil rate: schedule vs all wells at start', 'Sm³/d', colors={'Scheduled': charts.OIL, 'All wells at start': charts.LIQUID}, dash={'All wells at start': 'dot'}), use_container_width=True, key='sch_cmp_chart')
    b.plotly_chart(charts.lines(fdf, 'Date', ['Wells flowing'], 'Producers on stream', 'wells', colors={'Wells flowing': charts.CATEGORICAL[0]}), use_container_width=True, key='sch_wells')
    with st.expander('Full profile charts'):
        profile_charts(st, fc, key='_sch')
    st.markdown('### Browse the results')
    render_results_browser(st, nodes, edges, fc, key='sch_rb')
    with st.expander('Schedule table'):
        st.dataframe(sch, hide_index=True, use_container_width=True)


# --------------------------------------------------------------------------- scenarios
DEFAULT_SCENARIOS = pd.DataFrame([
    {'Scenario': 'Base', 'Wells': 'all', 'In-place ×': 1.0, 'PI ×': 1.0, 'Separator pressure [bar]': None, 'Liquid capacity [Sm3/d]': None, 'Injection': True},
    {'Scenario': 'Low in-place', 'Wells': 'all', 'In-place ×': 0.8, 'PI ×': 0.8, 'Separator pressure [bar]': None, 'Liquid capacity [Sm3/d]': None, 'Injection': True},
    {'Scenario': 'High in-place', 'Wells': 'all', 'In-place ×': 1.2, 'PI ×': 1.2, 'Separator pressure [bar]': None, 'Liquid capacity [Sm3/d]': None, 'Injection': True},
    {'Scenario': 'No injection', 'Wells': 'all', 'In-place ×': 1.0, 'PI ×': 1.0, 'Separator pressure [bar]': None, 'Liquid capacity [Sm3/d]': None, 'Injection': False},
])


def _kpi_table(results):
    rows = []
    for r in results:
        k = r['kpis']
        rows.append({'Scenario': r['name'], 'Peak oil [Sm3/d]': k.get('peak_oil_m3d'), 'Plateau [yr]': k.get('plateau_years'),
                     'Cum oil [MSm3]': (k.get('cum_oil_sm3') or 0) / 1e6, 'RF oil [%]': k.get('rf_oil_pct'),
                     'Final water cut [%]': k.get('final_water_cut_pct'), 'Cum gas [GSm3]': (k.get('cum_gas_sm3') or 0) / 1e9})
    return pd.DataFrame(rows)


def render_scenarios(st, nodes, edges):
    st.subheader('Development scenarios')
    st.caption('Each row is a complete forecast with explicit edits to a copy of the model: which producers are drilled, in-place and productivity multipliers, separator pressure, facility liquid capacity and whether injection runs.')
    with st.container(border=True):
        a, b, c, d = st.columns(4)
        start = a.date_input('Start date', value=DEFAULT_START, key='scn_start').isoformat()
        years = b.number_input('Horizon [years]', 1.0, 50.0, 15.0, 1.0, key='scn_years')
        step = c.selectbox('Report step [days]', [60, 90, 180, 365], index=1, key='scn_step')
        caps = d.toggle('Honour facility capacities', value=True, key='scn_caps')
        with st.expander('Schedule events applied to every scenario (optional)'):
            st.caption('Shut-ins, rate limits, pressure changes ... on top of each scenario edit. Shared with the Production forecast and Development schedule tabs.')
            scn_events = events_to_forecast(render_event_builder(st, nodes, edges, None, st.session_state.get('unit_profile', 'norwegian_si'), key_prefix='evb_scn', start_date=start))
        sdf = st.data_editor(DEFAULT_SCENARIOS, num_rows='dynamic', hide_index=True, use_container_width=True, key='scn_table',
                             column_config={'Wells': st.column_config.TextColumn(help="'all' or a comma-separated list of producer IDs/names"),
                                            'Separator pressure [bar]': st.column_config.NumberColumn(help='Blank = as in the model'),
                                            'Liquid capacity [Sm3/d]': st.column_config.NumberColumn(help='Blank = as in the model'),
                                            'Injection': st.column_config.CheckboxColumn()})
        rb = start_run(st, '▶ Run scenarios', key='scn_run', type='primary', model_hash=graph_hash(nodes, edges))
    if rb:
        scs = []
        for r in sdf.to_dict('records'):
            name = clean_text(r.get('Scenario'))
            if not name: continue
            scs.append({'name': name, 'wells': clean_text(r.get('Wells'), 'all') or 'all', 'in_place_mult': clean_num(r.get('In-place ×')),
                        'pi_mult': clean_num(r.get('PI ×')), 'separator_pressure_bar': clean_num(r.get('Separator pressure [bar]')),
                        'liquid_capacity_m3d': clean_num(r.get('Liquid capacity [Sm3/d]')), 'injection': bool(r.get('Injection')) if r.get('Injection') is not None else True,
                        'events': scn_events or None})
        rb.progress(0.02, 'Starting scenarios…')
        try:
            st.session_state.scn_results = run_scenarios(nodes, edges, scs, start, float(years), int(step), bool(caps), step_solver=_step_solver(st), workers=_workers(st), progress=lambda i, n: rb.progress(i / n, f'Scenario {i}/{n}'))
        except Exception as exc: rb.fail(f'Scenario run failed: {exc}')
        rb.finish()
    res = st.session_state.get('scn_results')
    if res:
        kt = _kpi_table(res)
        best = kt.sort_values('Cum oil [MSm3]', ascending=False).iloc[0]
        st.success(f"Highest cumulative oil: **{best['Scenario']}** — {best['Cum oil [MSm3]']:.2f} MSm³" + (f", RF {best['RF oil [%]']:.1f} %" if pd.notna(best['RF oil [%]']) else ''))
        st.dataframe(kt.style.format({c: '{:,.2f}' for c in kt.columns if c != 'Scenario'}, na_rep='—'), hide_index=True, use_container_width=True)
        long = pd.concat([pd.DataFrame(r['forecast']['field']).assign(Scenario=r['name']) for r in res], ignore_index=True)
        long['Cumulative oil [MSm3]'] = long['Cumulative oil [Sm3]'] / 1e6
        a, b = st.columns(2)
        a.plotly_chart(charts.by_category_lines(long, 'Date', 'Oil [m3/d]', 'Scenario', 'Oil rate by scenario', 'Sm³/d'), use_container_width=True, key='scn_oil')
        b.plotly_chart(charts.by_category_lines(long, 'Date', 'Cumulative oil [MSm3]', 'Scenario', 'Cumulative oil by scenario', 'MSm³'), use_container_width=True, key='scn_cum')
        st.download_button('Scenario KPIs CSV', kt.to_csv(index=False), 'fieldnet_scenarios.csv', 'text/csv')

    st.divider()
    st.subheader('How many wells?')
    st.caption('Forecasts the field with the first 1, 2, … N producers (in the order below) and recommends the well count where one more well stops adding a meaningful amount of oil.')
    prods = [n for n in nodes if n.get('kind') == 'well']
    if len(prods) < 2:
        st.info('Add at least two producers to run a well-count study.'); return
    names = {n['id']: n.get('name', n['id']) for n in prods}
    with st.container(border=True):
        order = st.multiselect('Producers in drilling priority', list(names), default=list(names), format_func=names.get, key='wc_order')
        thr = st.slider('Minimum extra oil from one more well [%]', 1, 30, 5, key='wc_thr')
        rbw = start_run(st, '▶ Run well-count study', key='wc_run', model_hash=graph_hash(nodes, edges), disabled=len(order) < 2)
    if rbw:
        rbw.progress(0.02, 'Starting well-count cases…')
        try:
            st.session_state.wc_result = well_count_study(nodes, edges, order, start, float(years), int(step), bool(caps), thr / 100.0, step_solver=_step_solver(st), workers=_workers(st),
                                                          progress=lambda i, n: rbw.progress(i / n, f'{i}/{n} well counts'))
            st.session_state.wc_names = names
        except Exception as exc: rbw.fail(f'Well-count study failed: {exc}')
        rbw.finish()
    wc = st.session_state.get('wc_result')
    if wc:
        rows = pd.DataFrame([{k: v for k, v in r.items() if k != '_forecast'} for r in wc['rows']])
        rows['Added well'] = rows['Added well'].map(lambda x: st.session_state.get('wc_names', {}).get(x, x))
        rows['Cum oil [MSm3]'] = rows['Cum oil [Sm3]'] / 1e6
        st.success(f"Recommended: **{wc['recommended_wells']} producer(s)**. {wc['reason']}")
        a, b = st.columns(2)
        a.plotly_chart(charts.bars(rows.assign(Label=rows['Wells'].astype(str)), 'Label', 'Cum oil [MSm3]', 'Cumulative oil vs number of producers', 'MSm³',
                                   text=[f"{v:.2f}" for v in rows['Cum oil [MSm3]']]), use_container_width=True, key='wc_bar')
        if rows['RF oil [%]'].notna().any():
            b.plotly_chart(charts.lines(rows, 'Wells', ['RF oil [%]'], 'Recovery factor vs number of producers', '%', colors={'RF oil [%]': charts.OIL}), use_container_width=True, key='wc_rf')
        st.dataframe(rows.drop(columns=['Cum oil [Sm3]']).style.format({'Cum oil [MSm3]': '{:.2f}', 'Incremental oil [Sm3]': '{:,.0f}', 'Incremental [%]': '{:.1f}', 'RF oil [%]': '{:.1f}', 'Peak oil [m3/d]': '{:,.0f}', 'Plateau [years]': '{:.1f}'}, na_rep='—'), hide_index=True, use_container_width=True)
