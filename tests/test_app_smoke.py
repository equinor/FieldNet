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
