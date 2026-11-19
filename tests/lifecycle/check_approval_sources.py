"""Compare only this change's BSL edits with its saved baseline and LS report."""
import difflib
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
run = root / '.local/lifecycle-approval'
before = (run / 'before.bsl').read_text(encoding='utf-8-sig')
after = (root / '1c/MCPToolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl').read_text(encoding='utf-8-sig')
pattern = r'// BEGIN GENERATED[^\n]*\n.*?// END GENERATED[^\n]*'
assert re.findall(pattern, before, re.S) == re.findall(pattern, after, re.S), 'Generated blocks changed'
changed = set()
for tag, a, b, c, d in difflib.SequenceMatcher(None, before.splitlines(), after.splitlines()).get_opcodes():
    if tag != 'equal':
        changed.update(range(c + 1, d + 1))
report = json.loads((run / 'bsl-result.json').read_text(encoding='utf-8-sig'))
findings = [d for d in report['diagnostics'] if d['line'] in changed]
errors = [d for d in findings if d['severity'] == 'Error']
result = dict(generated_blocks_unchanged=len(re.findall(pattern, before, re.S)),
              changed_lines=sorted(changed), diagnostics_total=report['diagnosticCount'],
              errors_total=report['errorCount'], changed_line_findings=findings,
              changed_line_errors=errors, source_sha256=hashlib.sha256(after.encode()).hexdigest())
(run / 'source-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k not in ('changed_lines', 'changed_line_findings')}, ensure_ascii=False))
assert not errors, errors
