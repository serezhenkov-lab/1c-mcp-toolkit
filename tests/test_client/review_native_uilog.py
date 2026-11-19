"""Offline review of a saved native recording. Does not dispatch any UI commands."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from onec_mcp_toolkit_proxy.scenario_import import import_uilog

run = Path(sys.argv[1])
raw = (run/'fresh-uilog.xml').read_bytes()
tree = ET.fromstring(raw)
original = import_uilog(raw, scenario_id='native-recording-851', policy_id='isolated-review-only')
assert original['status'] == 'blocked' and original['draft'] is None
assert original['dispatch_count'] == 0 and not original['execution_ready']

# Diagnostic derived copy only: expose the next unsupported event without
# changing production import rules or presenting edited XML as a fresh recording.
derived = ET.fromstring(raw)
for window in derived.findall('ClientApplicationWindow'):
    assert 'caption' in window.attrib and 'title' not in window.attrib
    window.set('title', window.attrib.pop('caption'))
derived_bytes = ET.tostring(derived, encoding='utf-8', xml_declaration=True)
diagnostic = import_uilog(derived_bytes, scenario_id='diagnostic-caption-only', policy_id='isolated-review-only')
assert diagnostic['status'] == 'blocked' and diagnostic['draft'] is None
assert len(diagnostic['candidate_steps']) == 1
assert sum(i['code'] == 'unsupported_event_target' for i in diagnostic['issues']) == 2
assert not any(i['code'] == 'ambiguous_recorded_target' for i in diagnostic['issues'])

def nodes(items):
    for n in items:
        yield n
        yield from nodes(n.get('children', []))

targets = []
for index, window in enumerate(tree.findall('ClientApplicationWindow')):
    snapshot_name = 'before-record-tree' if index == 0 else 'after-record-tree'
    snapshot = json.loads((run/(snapshot_name+'.json')).read_text(encoding='utf-8'))
    observed = list(nodes(snapshot['data']['tree']))
    forms = [n for n in observed if n.get('type') == 'form' and n.get('title') == window.get('caption')]
    assert len(forms) == 1
    for field in window.findall('./Form/FormField'):
        candidates = [n for n in observed if n.get('type') == 'field' and n.get('name') == field.get('name') and n.get('title') == field.get('title')]
        assert len(candidates) == 1
        targets.append(dict(snapshot=snapshot_name, caption=window.get('caption'), name=field.get('name'), title=field.get('title'),
                            matches_in_saved_snapshot=len(candidates), enabled=candidates[0]['enabled'], read_only=candidates[0]['read_only'],
                            events=[n.tag for n in field], live_execution_authorized=False))
before = json.loads((run/'baseline.json').read_text(encoding='utf-8'))
after = json.loads((run/'after-record-data.json').read_text(encoding='utf-8'))
assert before == after
assert json.loads((run/'cleanup.json').read_text(encoding='utf-8'))['all_exited']
report = dict(review_status='blocked', source_sha256=hashlib.sha256(raw).hexdigest(),
    source_is_platform_recording=True, recording_method='TestedApplication.StartUILogRecording/FinishUILogRecording',
    input_origin='public test_input, not a human recording', platform='8.5.1.1529',
    original_import_status=original['status'], original_draft=None, targets=targets,
    diagnostic_only=dict(transformation='ClientApplicationWindow.caption -> title, no event changes',
                         source_sha256=hashlib.sha256(derived_bytes).hexdigest(), report='diagnostic-import.json'),
    parameter_review=dict(value_count=len(diagnostic['parameter_values']), separate_from_template=True,
                          source='diagnostic candidate only, not an imported complete draft'),
    blockers=['caption_not_supported', 'false_sibling_ambiguity_without_caption_key', 'field_activate_not_representable',
              'mutable_form_title_requires_review'],
    baseline_unchanged=True, baseline_count=len(before), dispatch_count=0, execution_ready=False,
    decision='Do not drop activation events or execute the supported prefix; no reviewed/ready draft created')
(run/'diagnostic-caption-only.xml').write_bytes(derived_bytes)
for name,value in [('diagnostic-import',diagnostic),('uilog-review',report)]:
    (run/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(review='blocked', original_draft=None, recorded_events=3, reviewed_targets=len(targets), dispatch_count=0)))
