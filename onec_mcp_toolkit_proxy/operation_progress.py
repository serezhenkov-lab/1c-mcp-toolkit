"""Bounded executor progress: fixed facts only, no UI text or second journal."""
PHASES = {'executing', 'waiting', 'observing'}
STEPS = {'activate', 'open_choice_list', 'select_choice', 'toggle_check', 'clear',
         'input_text', 'finish_edit', 'action', 'add', 'open'}


def valid_progress(value):
    if not isinstance(value, dict) or set(value) != {'phase', 'completed_count', 'elapsed_ms', 'last_confirmed_step'}:
        return False
    phase, step = value['phase'], value['last_confirmed_step']
    return (isinstance(phase, str) and phase in PHASES
            and (step is None or (isinstance(step, str) and step in STEPS))
            and type(value['completed_count']) is int and 0 <= value['completed_count'] <= 1000000
            and type(value['elapsed_ms']) is int and 0 <= value['elapsed_ms'] <= 86400000
            and ((value['completed_count'] == 0) == (step is None)))


def public_progress(value, operation_id, sequence):
    return dict(value, operation_id=operation_id, sequence=sequence, scope='intermediate_snapshot')
