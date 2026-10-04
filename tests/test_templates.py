"""Template library: every template builds, is structurally valid, solves, and shows what it claims to show; UI loader through the harness."""
import os, pytest
from network.templates import TEMPLATES, build, catalogue, categories, pipe, PIPE_OIL, PIPE_GAS
from solver.v21 import solve_v21
from tests.support.app_harness import run_app
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py')
KEYS = list(TEMPLATES)


def test_registry_complete():
    need = {'hpht_4slot_gas', 'daisy_chain_oil', 'multi_tank_commingled', 'oil_gas_injection', 'pure_depletion_oil', 'wellhead_platform_tieback', 'subsea_booster_pump',
            'subsea_compressor_gas', 'topside_compressor_gas', 'horizontal_wells', 'hpht_tight_gas_frac'}
    assert need <= set(KEYS) and len(KEYS) >= 15
    for k, t in TEMPLATES.items():
        assert t['name'] and t['shows'] and t['watch'] and t['category'] in categories() and t['years'] > 0 and t['step'] in (30, 60, 90, 180, 365), k
    assert len(catalogue()) == len(KEYS)


@pytest.mark.parametrize('key', KEYS)
def test_structure(key):
    n, e = build(key); ids = [x['id'] for x in n]; eids = [x['id'] for x in e]
    assert len(set(ids)) == len(ids) and len(set(eids)) == len(eids)
    for x in e: assert x['source'] in ids and x['target'] in ids and x['source'] != x['target'], (key, x['id'])
    for x in n: assert all(isinstance(x.get(c), (int, float)) for c in ('x', 'y')), (key, x['id'])
    tanks = {x['id'] for x in n if x['kind'] == 'reservoir'}
    for w in n:
        if w['kind'] == 'well' and w['params'].get('reservoir_id'): assert w['params']['reservoir_id'] in tanks, (key, w['id'])
    for t in n:
        for c in (t.get('params') or {}).get('communication') or []: assert c['to'] in tanks, (key, t['id'])
    connected = {x['source'] for x in e} | {x['target'] for x in e}
    assert all(x['id'] in connected for x in n if x['kind'] != 'reservoir'), key
    a, b = build(key); a[0]['name'] = 'changed'; assert build(key)[0][0]['name'] != 'changed'


@pytest.mark.parametrize('key', KEYS)
def test_solves_and_flows(key):
    n, e = build(key); r = solve_v21(n, e)
    assert r[2]['success'] and r[2]['max_abs_residual'] < 1e-3, key
    wells = [x for x in n if x['kind'] == 'well']; flowing = [w for w in wells if (r[3].get(w['id']) or {}).get('status', 'flowing') == 'flowing' or abs(r[1].get(w['id'], 0)) > 0]
    assert wells and sum(abs(v) for v in r[1].values()) > 0 and flowing, key


@pytest.mark.parametrize('key', ['simple_well', 'gas_lift_field', 'waterflood_pattern', 'pure_depletion_oil'])
def test_short_forecast(key):
    from network.forecast import run_forecast
    n, e = build(key); fc = run_forecast(n, e, TEMPLATES[key]['start'], years=1, step_days=180)
    f = fc['field']; assert len(f) >= 2 and all(r['Converged'] for r in f) and f[0]['Wells flowing'] > 0 and f[-1]['Oil [m3/d]'] < f[0]['Oil [m3/d]'] * 1.01


def test_pump_and_compressors_show_benefit():
    for key, cid, ex, pg in (('subsea_booster_pump', 'BOOSTER', 'TIEBACK', PIPE_OIL), ('topside_compressor_gas', 'EXP-COMP', 'EXPORT', PIPE_GAS), ('subsea_compressor_gas', 'SUBSEA-COMP', 'TIEBACK', PIPE_GAS)):
        n, e = build(key)
        if key != 'subsea_booster_pump':
            for x in n:
                if x['kind'] in ('reservoir', 'well'): x['params']['reservoir_pressure_bar'] = 100.0
        with_eq = solve_v21(n, e); e2 = [x for x in e if x['id'] != cid] + [pipe('BYP', 'M1', 'M2', 50, 0.3, 0, **pg)]; without = solve_v21(n, e2)
        assert with_eq[1][ex] > without[1][ex] * 1.2, key


def test_gas_injection_and_multitank_and_horizontal_content():
    n, e = build('oil_gas_injection'); assert sum(1 for x in n if x['kind'] == 'gas_injector') == 2 and any(x['kind'] == 'compressor' for x in e)
    n, e = build('multi_tank_commingled'); assert sum(1 for x in n if x['kind'] == 'reservoir') == 3 and sum(len(x['params'].get('communication') or []) for x in n) >= 2 and sum(1 for x in n if x['kind'] == 'joint') == 2
    n, e = build('horizontal_wells'); hz = [x for x in n if x['kind'] == 'well' and x['params'].get('trajectory')]; assert hz and all(x['params'].get('completion') for x in hz)
    n, e = build('hpht_tight_gas_frac'); assert sum(1 for x in n if x['kind'] == 'well') == 8 and all(x['params']['skin'] < -3 for x in n if x['kind'] == 'well')
    n, e = build('hpht_4slot_gas'); assert sum(1 for x in n if x['kind'] == 'well') == 4 and max(x['params']['reservoir_pressure_bar'] for x in n if x['kind'] == 'reservoir') >= 700


def _no_errors(root):
    errs = [c for c in root.calls if c[0] in ('error', 'exception')]; assert not errs, errs


def test_loader_button_replaces_model_and_sets_forecast_defaults():
    from network.examples import demo_field_case
    n, e = demo_field_case()
    root = run_app(APP, {'nodes': n, 'edges': e, 'tpl_sel': 'subsea_booster_pump', 'tpl_cat': 'All', 'forecast': {'field': []}}, pressed={'tpl_load'}); _no_errors(root)
    ss = root.session_state; assert {x['id'] for x in ss['nodes']} == {x['id'] for x in build('subsea_booster_pump')[0]}
    assert ss['tpl_forecast']['template'] == 'subsea_booster_pump' and 'forecast' not in ss


def test_load_as_new_case_and_page_renders():
    from network.examples import demo_field_case
    n, e = demo_field_case(); _no_errors(run_app(APP, {'nodes': n, 'edges': e}))
    root = run_app(APP, {'nodes': n, 'edges': e, 'tpl_sel': 'daisy_chain_oil'}, pressed={'tpl_load_case'}); _no_errors(root)
    lib = root.session_state['case_library']; assert len(lib) == 1 and 'Daisy' in next(iter(lib.cases.values()))['name']


def test_templates_are_canvas_stable():
    """The canvas re-normalises the model on every move; a freshly loaded template must hash the same afterwards (no re-solve after moving a box)."""
    from ui.graph_contract import normalize_graph, graph_hash
    for k in KEYS:
        n, e = build(k); n2, e2, _ = normalize_graph(n, e); assert graph_hash(n, e) == graph_hash(n2, e2), k
        for x in n2: x['x'] = x['x'] + 37; x['y'] = x['y'] - 11
        assert graph_hash(n, e) == graph_hash(n2, e2), k


def test_old_models_with_default_edge_params_keep_hash():
    from ui.graph_contract import normalize_graph, graph_hash
    n, e = build('simple_well')
    for x in e: x['params'] = {}
    n2, e2, _ = normalize_graph(n, e); assert graph_hash(n, e) == graph_hash(n2, e2)


def test_sidebar_example_loader():
    from network.examples import demo_field_case
    n, e = demo_field_case()
    root = run_app(APP, {'nodes': n, 'edges': e, 'sb_tpl': 'hpht_tight_gas_frac'}, pressed={'sb_tpl_load'}); _no_errors(root)
    assert {x['id'] for x in root.session_state['nodes']} == {x['id'] for x in build('hpht_tight_gas_frac')[0]}
