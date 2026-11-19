"""Bounded uilog XML -> scenario-v1 draft. No execution, I/O or session binding.

Only explicitly mapped recorder events are converted. Unknown subtrees remain
addressable by source path/hash and block a complete draft; no successful prefix
is presented as the whole scenario. Original input remains owned by the caller.
"""
from copy import deepcopy
import hashlib
import json
import re
import xml.etree.ElementTree as ET

from .test_client_contract import valid_request


_ID = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z')
_CONTEXT = {'id', 'uid', 'pid', 'hwnd', 'port', 'session_id', 'operation_id',
            'request_id', 'snapshot_id', 'base', 'connectionString', 'user', 'password'}
_CONTAINERS = {'uilog': set(), 'ClientApplicationWindow': {'title', 'caption', 'isMain'},
               'Form': {'title'}, 'FormField': {'name', 'title'},
               'FormButton': {'name', 'title'}, 'FormGroup': {'name', 'title'}}
_PARENTS = {'ClientApplicationWindow': {'uilog'}, 'Form': {'uilog', 'ClientApplicationWindow'},
            'FormGroup': {'Form', 'FormGroup'},
            'FormField': {'Form', 'FormGroup'}, 'FormButton': {'Form', 'FormGroup'}}
_EVENTS = {'inputText', 'click', 'activate', 'close', 'setCheck'}
_FORBIDDEN = {'execute_code', 'executeCode', 'execute', 'script', 'BSL', 'eval',
              'Выполнить', 'ВыполнитьПроизвольныйКодКлиент', 'ВыполнитьПроизвольныйКодСервер'}


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def import_uilog(source, *, scenario_id, policy_id, purpose='Review imported UI recording'):
    """Return draft, separate parameter values and a non-executable review report.

    Supported encoding: UTF-8, with optional BOM. Limits: 1 MiB source,
    10,000 XML nodes, depth 32, 100 steps/parameters and 100 reported issues.
    No capability or live target uniqueness is inferred from a recording.
    """
    result = dict(version=1, status='rejected', draft=None, candidate_steps=[],
                  parameter_values={}, issues=[], issues_truncated=False,
                  targets_requiring_review=[], source_sha256=None,
                  dispatch_count=0, execution_ready=False)

    def issue(code, path='/', node=None, severity='error'):
        if len(result['issues']) >= 100:
            result['issues_truncated'] = True
            return
        result['issues'].append(dict(code=code, path=path, severity=severity,
            node_type=(node.tag[:128] if node is not None and isinstance(node.tag, str) else None),
            node_sha256=_hash(ET.tostring(node, encoding='utf-8')) if node is not None else None))

    if not (isinstance(scenario_id, str) and _ID.fullmatch(scenario_id)
            and isinstance(policy_id, str) and _ID.fullmatch(policy_id)
            and isinstance(purpose, str) and 0 < len(purpose) <= 4096):
        issue('invalid_import_options')
        return result
    try:
        raw = source.encode('utf-8') if isinstance(source, str) else source
        if not isinstance(raw, bytes):
            raise ValueError
        if len(raw) > 1024 * 1024:
            issue('input_budget_exceeded')
            return result
        result['source_sha256'] = _hash(raw)
        text = raw.decode('utf-8-sig')
        if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I):
            issue('forbidden_xml_declaration')
            return result
        # Reject unsupported encodings rather than letting XML declarations
        # select a second, potentially inconsistent decoder.
        declaration = re.match(r'\s*<\?xml\s+([^?]*)\?>', text)
        if declaration:
            encoding = re.search(r'encoding\s*=\s*[\'"]([^\'"]+)', declaration[1])
            if encoding and encoding[1].lower() not in ('utf-8', 'utf8'):
                issue('unsupported_encoding')
                return result
        tree = ET.fromstring(text, parser=ET.XMLParser(
            target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))
    except (ValueError, UnicodeError, ET.ParseError):
        issue('invalid_xml')
        return result
    if tree.tag != 'uilog':
        issue('unsupported_root', node=tree)
        return result
    pending, count = [(tree, 1)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth > 32 or count > 10000:
            issue('input_budget_exceeded')
            return result
        pending.extend((child, depth + 1) for child in node)

    steps, declarations = result['candidate_steps'], {}
    events = []
    blocked = False

    def block(code, path, node):
        nonlocal blocked
        blocked = True
        issue(code, path, node)

    def walk(node, path, parent=None, window=None, element=None, names=()):
        tag = node.tag
        if not isinstance(tag, str):
            block('unsupported_xml_node', path, node)
            return
        if tag in _FORBIDDEN:
            block('forbidden_event', path, node)
            return
        if tag not in _CONTAINERS and tag not in _EVENTS:
            block('unknown_event', path, node)
            return
        allowed = _CONTAINERS.get(tag, {'text'} if tag == 'inputText' else set())
        if set(node.attrib) - allowed - (_CONTEXT if tag in _CONTAINERS else set()):
            block('unknown_attribute', path, node)
            return
        if set(node.attrib) & _CONTEXT:
            issue('recorded_context_discarded', path, node, 'warning')
        if (node.text or '').strip() or any((child.tail or '').strip() for child in node):
            block('unexpected_node_text', path, node)
            return
        if any(len(v) > 65536 for k,v in node.attrib.items() if k not in _CONTEXT):
            block('input_budget_exceeded', path, node)
            return
        if tag in _CONTAINERS:
            if tag == 'uilog' and parent is not None:
                block('unsupported_hierarchy', path, node)
                return
            if tag != 'uilog' and parent not in _PARENTS[tag]:
                block('unsupported_hierarchy', path, node)
                return
            if tag in ('ClientApplicationWindow', 'Form'):
                if tag == 'ClientApplicationWindow' and 'caption' in node.attrib and 'title' in node.attrib and node.get('caption') != node.get('title'):
                    block('conflicting_window_title', path, node)
                    return
                title = node.get('caption') or node.get('title')
                if not title:
                    block('target_not_identified', path, node)
                    return
                window, element, names = {'selector': {'title': title}}, None, ()
            elif tag in ('FormField', 'FormButton', 'FormGroup'):
                selector = {k:node.attrib[k] for k in ('name', 'title') if node.get(k)}
                if not selector:
                    block('target_not_identified', path, node)
                    return
                selector['type'] = {'FormField':'field','FormButton':'button','FormGroup':'group'}[tag]
                # Names of ancestors are not automatically a proven Toolkit path.
                # Review records hierarchy separately; don't invent path semantics.
                element = {'selector':selector}
                names = names + (node.get('name') or node.get('title'),)
            # Duplicate sibling targets are ambiguous even before a live lookup.
            seen = set()
            for index, child in enumerate(node):
                child_path = f'{path}/{index}'
                # Top-level windows/forms are chronological recording blocks,
                # not a simultaneous inventory. Preserve every occurrence.
                if child.tag in _CONTAINERS and child.tag != 'uilog' and not (
                        tag == 'uilog' and child.tag in ('ClientApplicationWindow', 'Form')):
                    key = (child.tag, child.get('name'), child.get('title'))
                    if key in seen:
                        block('ambiguous_recorded_target', child_path, child)
                    seen.add(key)
                walk(child, child_path, tag, window, element, names)
            return
        if len(node):
            block('unexpected_event_children', path, node)
            return
        if window is None:
            block('target_not_identified', path, node)
            return
        event = dict(event=tag, source_path=path, node_sha256=_hash(ET.tostring(node, encoding='utf-8')),
                     window=deepcopy(window), element=deepcopy(element))
        if tag == 'activate' and parent == 'FormField':
            events.append(event)
            return
        if len(steps) >= 100:
            block('step_budget_exceeded', path, node)
            return
        action, tool, params, needs_element = None, None, {}, False
        if tag == 'inputText' and parent == 'FormField' and 'text' in node.attrib:
            tool, action, needs_element = 'test_input', 'text', True
            key = f'value_{len(steps)+1:03d}'
            params = {'text': {'$param':key}}
            declarations[key] = dict(type='string', required=True)
            result['parameter_values'][key] = node.attrib['text']
        elif tag == 'setCheck' and parent == 'FormField':
            tool, action, needs_element, params = 'test_input', 'check', True, {'checked':True}
        elif tag == 'click' and parent == 'FormButton':
            tool, action, needs_element = 'test_action', 'click', True
        elif tag in ('activate', 'close') and parent in ('ClientApplicationWindow', 'Form'):
            tool, action = 'test_action', 'activate_window' if tag == 'activate' else 'close'
        else:
            block('unsupported_event_target', path, node)
            return
        arguments = dict(action=action, params=params, window=deepcopy(window))
        if needs_element:
            arguments['element'] = deepcopy(element)
        materialized = deepcopy(arguments)
        if tag == 'inputText':
            materialized['params']['text'] = node.attrib['text']
        if not valid_request(tool, dict(materialized, request_id='import-shape', session_id='import-shape', timeout_ms=10000)):
            block('invalid_generated_arguments', path, node)
            return
        step_id = f'step_{len(steps)+1:03d}'
        steps.append(dict(step_id=step_id,tool=tool,arguments=arguments,on_error='stop',timeout_ms=10000))
        event['step_id'] = step_id
        events.append(event)
        result['targets_requiring_review'].append(dict(step_id=step_id, source_path=path,
            recorded_hierarchy=list(names), reason='live_uniqueness_and_capability_unproven'))

    walk(tree, '/uilog')
    # A draft-only composition proposal, never an authorization to discard focus
    # events. Prefix activation is intrinsic to test_input. The recorded finish
    # target and same-form relationship require review against the driver/UI.
    compositions = []
    consumed = set()
    for i, event in enumerate(events):
        if event['event'] != 'inputText' or 'step_id' not in event or i == 0:
            continue
        prefix = events[i-1]
        if (prefix['event'] != 'activate' or 'step_id' in prefix
                or prefix['window'] != event['window'] or prefix['element'] != event['element']):
            continue
        consumed.add(i-1)
        group = dict(step_id=event['step_id'], rule='activate_then_input',
                     events=[deepcopy(prefix), deepcopy(event)],
                     obligations=['confirm_live_target_and_input_activation'])
        if i+1 < len(events):
            suffix = events[i+1]
            title = event['window']['selector']['title']
            suffix_title = suffix['window']['selector']['title']
            followed_by_input = i+2 < len(events) and events[i+2]['event'] == 'inputText'
            if (suffix['event'] == 'activate' and 'step_id' not in suffix and not followed_by_input
                    and suffix['element'] != event['element']
                    and suffix_title in (title, title + ' *')):
                consumed.add(i+1)
                group['rule'] = 'activate_input_finish_candidate'
                group['events'].append(deepcopy(suffix))
                group['obligations'] += ['confirm_same_form_across_blocks', 'confirm_exact_finish_target']
                step = next(s for s in steps if s['step_id'] == event['step_id'])
                step['finish_focus'] = dict(selector=deepcopy(suffix['element']['selector']), same_form=True)
        compositions.append(group)
    for i, event in enumerate(events):
        if event['event'] == 'activate' and 'step_id' not in event and i not in consumed:
            blocked = True
            issue('unmapped_field_activation', event['source_path'])
    if not steps:
        block('no_supported_steps', '/uilog', tree)
    draft = dict(version=1,scenario_id=scenario_id,revision=1,state='draft',
                 parameters=declarations,data_scope=dict(policy_id=policy_id,purpose=purpose,mutation='ui_write'),
                 steps=deepcopy(steps))
    if compositions:
        draft['recording_review'] = dict(source_sha256=result['source_sha256'], compositions=compositions)
        result['targets_requiring_review'].extend(dict(step_id=c['step_id'],
            source_path=c['events'][0]['source_path'], reason='recorded_activation_composition_unproven',
            obligations=deepcopy(c['obligations'])) for c in compositions)
    if len(json.dumps(draft,ensure_ascii=False).encode('utf-8')) > 256 * 1024:
        block('draft_budget_exceeded', '/uilog', tree)
    result['status'] = 'blocked' if blocked else 'draft'
    if not blocked:
        result['draft'] = draft
    # Candidates are for manual review only and never form a successful prefix.
    return result
