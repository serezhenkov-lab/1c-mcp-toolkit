"""Check recorded platform observations, including counterexamples to selection identity."""
import json
from pathlib import Path
import sys

source = Path(sys.argv[1])
records = json.loads(source.read_text(encoding='utf-8-sig'))
assert all(r['ok'] for r in records), records
data = {r['name']: json.loads(r['details']) for r in records}
search = data['directed_search_observed']
marker = data['selection_marker_observed']
native = data['native_ids_observed']
checks = {
    'directed_search_includes_current': search['current_down'] and search['current_up'] and search['last_down'],
    'missing_is_exception': bool(search['missing_error']),
    'shift_distinguishes_duplicate_rows': marker['first_count'] == 1 and marker['shift_next_count'] == 2,
    'end_is_exception': bool(marker['shift_end_error']) and marker['shift_end_count'] == 2,
    'selection_identity_counterexample': marker['before_external_switch_count'] == marker['after_external_switch_count'] == 1
        and marker['toggle_after_switch_count'] == 0 and marker['physical_switch_confirmed'],
    'native_repeat_stable': native['first'] == native['repeat_first'],
    'native_duplicate_rows_distinct': native['first']['current_id'] != native['second']['current_id'],
    'native_same_form': len({v['form_id'] for v in native.values()}) == 1,
    'native_sort_preserves_current': native['second']['current_id'] == native['after_sort']['current_id'],
    'native_move_preserves_ids': native['after_move']['row_ids'] == native['first']['row_ids'][::-1],
    'native_replace_does_not_reuse_deleted_id': native['after_move']['row_ids'][0] not in native['after_replace']['row_ids'],
    'native_clear_does_not_reuse_previous_ids': not set(native['after_clear']['row_ids']) & set(native['after_replace']['row_ids']),
}
output = source.with_name('verified.json')
output.write_text(json.dumps(checks, indent=2), encoding='utf-8')
assert all(checks.values()), checks
print(f'{len(checks)}/{len(checks)} platform observations verified')
