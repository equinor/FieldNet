"""Tank coupling summaries derived from the canvas model (no separate tables to keep in sync)."""
from __future__ import annotations
import pandas as pd

WELLS = ('well',); INJ = ('water_injector', 'gas_injector', 'injector')


def tank_coupling_table(nodes, edges=None):
    rows = []
    byid = {n['id']: n for n in nodes}
    for t in nodes:
        if t.get('kind') != 'reservoir': continue
        p = t.get('params') or {}; ph = p.get('fluid_phase', 'oil')
        drains = [w.get('name', w['id']) for w in nodes if w.get('kind') in WELLS and (w.get('params') or {}).get('reservoir_id') == t['id']]
        supports = [w.get('name', w['id']) for w in nodes if w.get('kind') in INJ and (w.get('params') or {}).get('reservoir_id') == t['id']]
        links = [byid[c['to']].get('name', c['to']) for c in p.get('communication') or [] if c.get('to') in byid]
        links += [n.get('name', n['id']) for n in nodes if n.get('kind') == 'reservoir' for c in (n.get('params') or {}).get('communication') or [] if c.get('to') == t['id']]
        inplace = (float(p.get('stoiip_sm3') or 0) / 1e6, 'MSm³ oil') if ph == 'oil' else (float(p.get('giip_sm3') or 0) / 1e9, 'GSm³ gas')
        rows.append({'Tank': t.get('name', t['id']), 'Phase': ph, 'In place': f'{inplace[0]:,.2f} {inplace[1]}', 'Initial pressure [bar]': p.get('reservoir_pressure_bar'),
                     'Producers': ', '.join(drains) or '—', 'Injectors': ', '.join(supports) or '—', 'Aquifer PI [m3/d/bar]': p.get('aquifer_pi_m3d_bar', 0) or 0,
                     'Communicates with': ', '.join(links) or '—', 'Relperm': 'yes' if p.get('relperm') else 'screening S-curve'})
    return pd.DataFrame(rows)


def communication_table(nodes):
    byid = {n['id']: n for n in nodes}; rows = []
    for t in nodes:
        for c in (t.get('params') or {}).get('communication') or []:
            if c.get('to') in byid:
                rows.append({'From': t.get('name', t['id']), 'To': byid[c['to']].get('name', c['to']), 'Transmissibility [m3/d/bar]': c.get('transmissibility_m3d_bar', 100.0),
                             'Max transfer [m3/d] (blank = none)': c.get('max_transfer_m3d'), '_from_id': t['id'], '_to_id': c['to']})
    return pd.DataFrame(rows)


def apply_communication_table(nodes, df):
    """Write edited values back; returns True when anything changed."""
    byid = {n['id']: n for n in nodes}; changed = False
    for r in df.to_dict('records'):
        t = byid.get(r.get('_from_id'))
        if not t: continue
        for c in (t.get('params') or {}).get('communication') or []:
            if c.get('to') != r.get('_to_id'): continue
            T = r.get('Transmissibility [m3/d/bar]'); M = r.get('Max transfer [m3/d] (blank = none)')
            try: T = float(T)
            except (TypeError, ValueError): T = c.get('transmissibility_m3d_bar', 100.0)
            try: M = float(M) if M == M and M not in (None, '') and float(M) > 0 else None
            except (TypeError, ValueError): M = None
            if abs(float(c.get('transmissibility_m3d_bar') or 0) - T) > 1e-12 or c.get('max_transfer_m3d') != M:
                c['transmissibility_m3d_bar'] = max(T, 0.0); c['max_transfer_m3d'] = M; changed = True
    return changed
