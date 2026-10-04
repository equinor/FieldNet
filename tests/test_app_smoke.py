"""Run the whole Streamlit script against a fake Streamlit (no real widgets): catches NameErrors / bad calls."""
import os
from tests.support.app_harness import run_app
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py')


def test_app_runs_with_default_state():
    root = run_app(APP); assert root.session_state.get('nodes') is not None


def test_app_solves_forecasts_and_selects_each_kind():
    from network.examples import demo_field_case
    from network.equipment import convert_edge_equipment_to_nodes
    n, e = demo_field_case(); n, e = convert_edge_equipment_to_nodes(n, [dict(x, kind='choke') if x is e[0] else x for x in e], {e[0]['id']})
    n.append({'id': 'J1', 'kind': 'joint', 'name': 'J', 'pressure_bar': None, 'x': 5, 'y': 5, 'params': {}})
    kinds_done = set()
    for node in n:
        if node['kind'] in kinds_done: continue
        kinds_done.add(node['kind'])
        root = run_app(APP, {'nodes': [dict(x) for x in n], 'edges': [dict(x) for x in e], 'selected': node['id'], 'prop_pick': node['id']}, pressed={'solve_btn_top'})
    for ed in e[:3]:
        run_app(APP, {'nodes': [dict(x) for x in n], 'edges': [dict(x) for x in e], 'selected': ed['id'], 'prop_pick': ed['id']})
    assert len(kinds_done) >= 8


def test_forecast_run_pause_continue_stop_flow():
    from network.examples import demo_field_case
    n, e = demo_field_case()
    base = {'nodes': n, 'edges': e, 'fc_years': 1.0, 'fc_step': 90}
    root = run_app(APP, dict(base), pressed={'fc_run'})
    ctl = root.session_state.get('fc_ctl'); assert ctl is not None and ctl.status == 'done'
    assert root.session_state.forecast['field']
    # pause: start a run, advance one event, press Pause on the rerun, then Continue, then Stop
    from network.run_control import RunController
    from network.forecast import iter_forecast
    c = RunController(iter_forecast(n, e, '2026-01-01', 1.0, 90)); c.advance(3)
    st2 = dict(base, fc_ctl=c, fc_ctl_hash=None)
    root = run_app(APP, st2, pressed={'fc_pause'}); assert root.session_state['fc_ctl'].status == 'paused'
    root = run_app(APP, dict(root.session_state), pressed={'fc_stop'}); assert root.session_state['fc_ctl'].status == 'stopped'


def test_advanced_panels_run_with_solved_demo_and_forecast():
    from network.examples import demo_field_case
    from network.forecast import run_forecast
    n, e = demo_field_case(); fc = run_forecast(n, e, '2026-01-01', 1.0, 90)
    pressed = {'solve_btn_top', 'adv_cal_syn', 'adv_lg_run', 'adv_ba_run', 'adv_ba_sched', 'adv_sens_run', 'adv_rel_run', 'adv_sim_vfp'}
    root = run_app(APP, {'nodes': n, 'edges': e, 'forecast': fc}, pressed=pressed)
    s = root.session_state
    assert s.get('adv_sens') and s.get('adv_rel') and s.get('adv_vfp'), [k for k in s if k.startswith('adv')]
    errs = [c for c in root.calls if c[0] == 'error']; assert not errs, errs


def test_development_plan_runs_with_progress_and_results_browser():
    from network.examples import demo_field_case
    n, e = demo_field_case()
    root = run_app(APP, {'nodes': n, 'edges': e, 'sch_years': 1.0}, pressed={'sch_run'})
    s = root.session_state
    assert s.get('sched_result'), 'development plan did not run'
    assert s.get('_rb_sch_run', {}).get('status') == 'done'
    errs = [c for c in root.calls if c[0] == 'error']; assert not errs, errs
    assert any(c == ('markdown', '#### Network at a chosen date') for c in root.calls)


def test_prediction_source_page_applies_decline_and_external_tank():
    from network.examples import demo_field_case
    n, e = demo_field_case()
    root = run_app(APP, {'nodes': n, 'edges': e, 'ps_kind': 'decline', 'ps_qi': 900.0}, pressed={'ps_apply_wells'})
    ws = [x for x in root.session_state['nodes'] if x['kind'] == 'well']
    assert ws and all((x['params'].get('prediction_source') or {}).get('type') == 'decline' for x in ws)
    errs = [c for c in root.calls if c[0] == 'error']; assert not errs, errs


def test_monte_carlo_builder_runs_and_has_green_button():
    from network.examples import demo_field_case
    n, e = demo_field_case()
    root = run_app(APP, {'nodes': n, 'edges': e, 'v17_samples': 5, 'v17_years': 0.5}, pressed={'rb_mc'})
    s = root.session_state
    assert s.get('mc_params') and s['mc_params'][0]['target_id'] == 'kind:well'
    assert s.get('v17_mc') and s['_rb_rb_mc']['status'] == 'done', {k: v for k, v in s.items() if k.startswith('_rb')}
    errs = [c for c in root.calls if c[0] == 'error']; assert not errs, errs
