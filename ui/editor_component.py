from pathlib import Path
import streamlit.components.v1 as components

_BUILD = Path(__file__).parent / 'fieldnet_canvas' / 'build'
_component = components.declare_component('fieldnet_canvas_current', path=str(_BUILD))

def network_editor(nodes, edges, results=None, *, solve_state=None, viewport=None, height=820, key='fieldnet-editor'):
    p,q,info,_ = results if results else ({},{},{},{})
    state = dict(solve_state or {})
    if results and not state:
        state={'status':'SOLVED' if info.get('quality_gate')=='PASS' else 'FAILED','quality_gate':info.get('quality_gate'),'message':info.get('message','')}
    return _component(nodes=nodes, edges=edges, pressures=p, rates=q, solve_state=state,
                      viewport=viewport or {'zoom':1.0,'scrollLeft':0,'scrollTop':0},
                      height=height, key=key, default=None)
