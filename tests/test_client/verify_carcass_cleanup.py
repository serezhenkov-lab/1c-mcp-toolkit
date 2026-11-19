"""Verify cleanup against the actual Designer export and preserved original files."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / '.local/http-mvp'
fixture = json.loads((Path(__file__).parent / 'carcass-fixtures.json').read_text(encoding='utf-8'))
hashes = json.loads((RUN / 'cleanup-original-hashes.json').read_text(encoding='utf-8'))
ns = {'m': 'http://v8.1c.ru/8.3/MDClasses', 'r': 'http://v8.1c.ru/8.2/roles'}
retained = {v['object'] for v in fixture['missing_examples_retained']} | set(fixture['infrastructure'])
results = {}
for source in (ROOT / fixture['source'], RUN / 'carcass-final-verified'):
    tree = ET.parse(source / 'Configuration.xml')
    children = tree.find('m:Configuration/m:ChildObjects', ns)
    names = {e.tag.rsplit('}', 1)[-1] + '.' + e.text for e in children}
    added = {name for name in names if name.split('.', 1)[1].startswith('МВП')}
    assert added == retained, (source, added, retained)
    assert not set(fixture['removed']) & names
    for role_object in ET.parse(source / 'Roles/МВППолныеПрава/Ext/Rights.xml').findall('r:object/r:name', ns):
        assert not any(role_object.text == old or role_object.text.startswith(old + '.') for old in fixture['removed'])
    role = ET.parse(source / 'Roles/МВППолныеПрава.xml').find('m:Role', ns)
    assert role.get('uuid') == '17b8695f-f39a-4000-8c2f-bf2314e49bc0'
    assert not tree.find('m:Configuration/m:Properties/m:DefaultConstantsForm', ns).text
    unchanged = []
    for relative, digest in hashes.items():
        path = source / relative
        assert path.is_file(), (source, 'missing original file', relative)
        if relative in fixture['existing_form_adjustments']:
            # Only the declared two scalar bindings may differ in the original form.
            original = RUN / 'carcass-verified-after-cleanup' / relative
            form_ns = {'f': 'http://v8.1c.ru/8.3/xcf/logform'}
            before = ET.parse(original).getroot()
            after = ET.parse(path).getroot()
            items = after.find('f:ChildItems', form_ns)
            added_fields = [e for e in items if e.get('name') in ('ДатаНачала', 'ДатаОкончания')]
            assert len(added_fields) == 2
            for field in added_fields:
                binding = field.find('f:DataPath', form_ns).text
                assert binding in ('ВыборПериода.ДатаНачала', 'ВыборПериода.ДатаОкончания', 'ВыборПериода.StartDate', 'ВыборПериода.EndDate')
                items.remove(field)
            assert ET.tostring(after) == ET.tostring(before), (source, 'unexpected form change', relative)
            continue
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, (source, 'changed original file', relative)
        unchanged.append(relative)
    for path in source.rglob('*'):
        if path.is_file() and path.suffix in ('.xml', '.bsl'):
            text = path.read_text(encoding='utf-8-sig')
            assert not any(old.split('.', 1)[1] in text for old in fixture['removed']), path
    results[source.name] = {'metadata_objects': len(names), 'retained_additions': sorted(added),
                            'unchanged_original_files': len(unchanged), 'declared_form_adjustments': fixture['existing_form_adjustments'], 'removed_objects': fixture['removed']}
(RUN / 'cleanup-verification.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
