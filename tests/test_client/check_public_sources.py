"""Check only this interval's edits, without treating existing LS errors as clean."""
import difflib
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
run = root / '.local/queue1'
report = json.loads((run / 'bsl-result.json').read_text(encoding='utf-8-sig'))
result = {'diagnostics_total': report['diagnosticCount'], 'errors_total': report['errorCount'], 'modules': []}
for name, form in [('main', 'Форма'), ('driver', 'ФормаМенеджераТестирования')]:
    path = root / '1c/MCPToolkit/MCPToolkit/Forms' / form / 'Ext/Form/Module.bsl'
    before = (run / (name + '-before.bsl')).read_text(encoding='utf-8-sig')
    after = path.read_text(encoding='utf-8-sig')
    changed = set()
    for tag, a, b, c, d in difflib.SequenceMatcher(None, before.splitlines(), after.splitlines()).get_opcodes():
        if tag != 'equal':
            changed.update(range(c + 1, d + 1))
    diagnostics = [item for item in report['diagnostics'] if Path(item['path']) == path and item['line'] in changed]
    pattern = r'// BEGIN GENERATED[^\n]*\n.*?// END GENERATED[^\n]*'
    generated = re.findall(pattern, before, re.S)
    assert generated == re.findall(pattern, after, re.S), path
    errors = [item for item in diagnostics if item['severity'] == 'Error']
    result['modules'].append(dict(path=str(path.relative_to(root)), changed_line_count=len(changed),
                                  generated_unchanged=len(generated), changed_line_diagnostics=diagnostics,
                                  changed_line_errors=errors, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(run / 'source-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print([(item['path'], item['changed_line_count'], len(item['changed_line_errors']), item['generated_unchanged']) for item in result['modules']])
assert not any(item['changed_line_errors'] for item in result['modules'])
