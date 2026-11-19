"""Pure, bounded query comparison (TASK-020 contract v1).

Inputs must come from a trusted collector, after existing data handling. This
module performs no I/O and grants no authority to supplied provenance claims.
"""
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import re
from uuid import UUID


TYPES = {'string', 'number', 'boolean', 'datetime', 'uuid', 'reference'}
CONTRACT_FIELDS = set('id base_id query_fingerprint schema mode keys order_basis ignore_columns data_policy_id'.split())
SOURCE_FIELDS = set('kind base_id query_fingerprint data_policy_id read_id operation_id started_at finished_at status coverage effective_limit fidelity order_proven normalization_error'.split())
NORMALIZATION_ERRORS = {'ambiguous_null', 'ambiguous_type', 'numeric_precision_unproven',
                        'unsupported_value', 'schema_unavailable', 'malformed_source'}
NUMBER = re.compile(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?\Z')
UUID_PATTERN = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z')
REFERENCE = re.compile(r'(?:СправочникСсылка|ДокументСсылка)\.[^\s.]+\Z')


class _Rejected(Exception):
    def __init__(self, reason, status='unavailable'):
        self.reason, self.status = reason, status


def _require(condition, reason='invalid_shape', status='invalid_contract'):
    if not condition:
        raise _Rejected(reason, status)


def _fields(value, fields):
    _require(isinstance(value, Mapping) and set(value) == fields)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))


def _schema(value):
    _require(isinstance(value, list) and bool(value))
    _require(len(value) <= 100, 'input_budget_exceeded', 'unavailable')
    names = []
    for col in value:
        _fields(col, {'name', 'type', 'null_policy'})
        _require(_text(col['name']) and col['type'] in TYPES)
        _require(col['null_policy'] in ('reject', 'wire_null'))
        names.append(col['name'])
    _require(len(set(names)) == len(names))
    return {c['name']: c for c in value}


def _contract(c):
    _require(isinstance(c, Mapping))
    _require(not (set(c) - CONTRACT_FIELDS), 'unsupported_rule')
    _fields(c, CONTRACT_FIELDS)
    for name in ('id', 'base_id', 'data_policy_id'):
        _require(_text(c[name]))
    _require(isinstance(c['query_fingerprint'], str) and re.fullmatch('[0-9a-f]{64}', c['query_fingerprint']))
    cols = _schema(c['schema'])
    _require(c['mode'] in ('bag', 'keyed', 'ordered'))
    keys = c['keys']
    _require(isinstance(keys, list) and all(isinstance(k, str) for k in keys))
    _require(len(set(keys)) == len(keys) and all(k in cols for k in keys))
    _require(bool(keys) == (c['mode'] == 'keyed'))
    _require(all(cols[k]['null_policy'] == 'reject' for k in keys))
    _require(_text(c['order_basis']) if c['mode'] == 'ordered' else c['order_basis'] is None)
    _require(isinstance(c['ignore_columns'], list))
    ignored = []
    for item in c['ignore_columns']:
        _fields(item, {'name', 'reason'})
        _require(isinstance(item['name'], str) and item['name'] in cols and item['name'] not in keys)
        _require(_text(item['reason']))
        ignored.append(item['name'])
    _require(len(set(ignored)) == len(ignored) and len(ignored) < len(cols))
    return cols, [name for name in cols if name not in ignored]


def _source(s):
    _fields(s, SOURCE_FIELDS)
    for name in ('kind', 'base_id', 'query_fingerprint', 'data_policy_id', 'read_id'):
        _require(_text(s[name]))
    _require(s['operation_id'] is None or _text(s['operation_id']))
    _require(s['status'] in ('success', 'failed', 'unknown'))
    _require(s['coverage'] in ('complete', 'partial', 'unknown'))
    _require(s['fidelity'] in ('exact', 'wire_projection', 'unknown'))
    _require(type(s['order_proven']) is bool)
    _require(s['normalization_error'] is None or s['normalization_error'] in NORMALIZATION_ERRORS)
    limit = s['effective_limit']
    _require(limit is None or type(limit) is int and limit > 0)
    times = []
    for name in ('started_at', 'finished_at'):
        _require(isinstance(s[name], str))
        try:
            stamp = datetime.fromisoformat(s[name].replace('Z', '+00:00'))
            _require(stamp.utcoffset() == timezone.utc.utcoffset(stamp))
            times.append(stamp)
        except ValueError:
            raise _Rejected('invalid_shape', 'invalid_contract') from None
    _require(times[0] <= times[1])


def _uuid(value):
    _require(isinstance(value, str) and UUID_PATTERN.fullmatch(value))
    return str(UUID(value))


def _cell(cell, col):
    _fields(cell, {'type', 'value'})
    kind, value = cell['type'], cell['value']
    if kind == 'wire_null':
        _require(value is None)
        _require(col['null_policy'] == 'wire_null', 'ambiguous_null', 'unavailable')
        return kind, None
    _require(kind in TYPES)
    if kind == 'string':
        _require(isinstance(value, str))
    elif kind == 'number':
        _require(isinstance(value, str) and NUMBER.fullmatch(value))
        value = Decimal(value)  # No context-dependent normalize()/rounding.
    elif kind == 'boolean':
        _require(type(value) is bool)
    elif kind == 'datetime':
        _require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value))
        try:
            datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            raise _Rejected('invalid_shape', 'invalid_contract') from None
    elif kind == 'uuid':
        value = _uuid(value)
    elif kind == 'reference':
        _fields(value, {'object_type', 'id', 'presentation'})
        _require(isinstance(value['object_type'], str) and REFERENCE.fullmatch(value['object_type']))
        _require(value['presentation'] is None or isinstance(value['presentation'], str))
        identity = _uuid(value['id'])
        _require(UUID(identity).int != 0)
        value = (value['object_type'], identity)
    return kind, value


def _empty_result():
    return dict(version=1, contract_id=None, status='unavailable', equal=None,
                reason=None, scope=None, sources={}, applied_rules={},
                counts=dict.fromkeys(('expected', 'actual', 'missing', 'unexpected', 'changed', 'equal')),
                diff={k: [] for k in ('schema', 'missing', 'unexpected', 'changed')},
                diff_truncated=False, business_confirmed=False)


def _bounded_diff(result):
    kept = {k: [] for k in ('schema', 'missing', 'unexpected', 'changed')}
    count, stopped = 0, False
    for kind, entries in result['diff'].items():
        for entry in entries:
            if stopped or count == 100:
                stopped = True
                continue
            kept[kind].append(entry)
            if _size(kept) > 256 * 1024:
                kept[kind].pop()
                stopped = True
            else:
                count += 1
    result['diff'], result['diff_truncated'] = kept, stopped


def compare_query_results(request: Mapping) -> dict:
    """Compare trusted normalized inputs; never execute or retry a command."""
    result = _empty_result()
    try:
        _compare(request, result)
        _bounded_diff(result)
        return deepcopy(result)
    except _Rejected as error:
        result.update(status=error.status, equal=None, reason=error.reason, scope=None)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        result.update(status='invalid_contract', equal=None, reason='invalid_shape', scope=None)
    except Exception:
        # Do not expose exception text or data; no logging/retry side effect.
        result.update(status='unavailable', equal=None, reason='comparison_failed', scope=None)
    result['diff'] = {k: [] for k in result['diff']}
    for k in ('missing', 'unexpected', 'changed', 'equal'):
        result['counts'][k] = None
    return deepcopy(result)


def _compare(request, out):
    _fields(request, {'version', 'contract', 'expected', 'actual'})
    _require(type(request['version']) is int and request['version'] == 1)
    _require(_size(request) <= 1024 * 1024, 'input_budget_exceeded', 'unavailable')
    c = request['contract']
    cols, projected = _contract(c)
    out['contract_id'] = c['id']
    out['applied_rules'] = {k: deepcopy(c[k]) for k in ('mode', 'keys', 'order_basis', 'ignore_columns', 'data_policy_id')}
    out['applied_rules']['null_policy'] = {k: v['null_policy'] for k, v in cols.items()}
    datasets = [request['expected'], request['actual']]
    for side, data in zip(('expected', 'actual'), datasets):
        try:
            _fields(data, {'source', 'schema', 'rows'})
            _source(data['source'])
            _require(data['rows'] is None or isinstance(data['rows'], list))
        except (_Rejected, TypeError, ValueError):
            raise _Rejected('invalid_shape', 'invalid_contract') if side == 'expected' else _Rejected('malformed_source')
        out['sources'][side] = deepcopy(data['source'])
        if isinstance(data['rows'], list):
            _require(len(data['rows']) <= 1000, 'input_budget_exceeded', 'unavailable')
            out['counts'][side] = len(data['rows'])
    for data, kind in zip(datasets, ('baseline', 'execute_query')):
        s = data['source']
        _require(s['kind'] == kind, 'unsupported_source', 'unavailable')
        _require(s['status'] == 'success', 'source_' + s['status'], 'unavailable')
        _require(all(s[k] == c[k] for k in ('base_id', 'query_fingerprint', 'data_policy_id')), 'source_mismatch', 'unavailable')
    for data in datasets:
        s = data['source']
        if s['kind'] == 'execute_query':
            limit = s['effective_limit']
            _require(type(limit) is int and limit > 0, 'malformed_source', 'unavailable')
            if data['rows'] is not None:
                _require(len(data['rows']) <= limit, 'malformed_source', 'unavailable')
                _require(len(data['rows']) < limit, 'incomplete_source', 'unavailable')
        _require(s['coverage'] == 'complete', 'incomplete_source', 'unavailable')
        _require(s['normalization_error'] is None, s['normalization_error'], 'unavailable')
        _require(s['fidelity'] != 'unknown', 'fidelity_unproven', 'unavailable')
        if s['fidelity'] == 'wire_projection':
            _require(bool(c['ignore_columns']) or any(v['null_policy'] == 'wire_null' for v in cols.values()), 'fidelity_unproven', 'unavailable')
    schemas, rows, tokens = [], [], []
    for side, data in zip(('expected', 'actual'), datasets):
        _require(data['schema'] is not None, 'schema_unavailable', 'unavailable')
        if isinstance(data['schema'], list):
            for col in data['schema']:
                if isinstance(col, Mapping) and isinstance(col.get('type'), str):
                    _require(col['type'] in TYPES, 'schema_unavailable', 'unavailable')
        try:
            schema = _schema(data['schema'])
            _require(isinstance(data['rows'], list))
            side_rows, side_tokens = [], []
            for row in data['rows']:
                _require(isinstance(row, list) and len(row) == len(schema))
                mapped = dict(zip(schema, row))
                typed = {k: _cell(mapped[k], col) for k, col in schema.items()}
                if side == 'expected':
                    _require(all(typed[k][0] in (schema[k]['type'], 'wire_null') for k in schema))
                side_rows.append(mapped)
                side_tokens.append(typed)
        except _Rejected as error:
            if error.status == 'invalid_contract' and side == 'actual':
                raise _Rejected('malformed_source') from None
            raise
        schemas.append(schema)
        rows.append(side_rows)
        tokens.append(side_tokens)
    _require(schemas[0] == cols)
    projection = bool(c['ignore_columns']) or any(v['null_policy'] == 'wire_null' for v in cols.values())
    out['scope'] = 'wire_projection' if projection else 'query_result'
    for name in list(cols) + [k for k in schemas[1] if k not in cols]:
        if cols.get(name) != schemas[1].get(name):
            out['diff']['schema'].append(dict(column=name, expected=cols.get(name), actual=schemas[1].get(name)))
    if out['diff']['schema']:
        out.update(status='different', equal=False, reason='schema_mismatch')
        return
    if c['mode'] == 'ordered':
        _require(all(d['source']['order_proven'] for d in datasets), 'order_unproven', 'unavailable')
    def signature(row, names):
        return tuple(row[k] for k in names)
    def groups(side, names):
        found = defaultdict(list)
        for i, row in enumerate(tokens[side]):
            found[signature(row, names)].append(i)
        return found
    def absent(kind, side, indices):
        out['diff'][kind].append(dict(row=[rows[side][indices[0]][k] for k in cols], count=len(indices), indices=indices))
        out['counts'][kind] += len(indices)
    def pair(e, a):
        cells = [dict(column=k, expected=rows[0][e][k], actual=rows[1][a][k])
                 for k in projected if tokens[0][e][k] != tokens[1][a][k]]
        if cells:
            out['counts']['changed'] += 1
            out['diff']['changed'].append(dict(expected_index=e, actual_index=a,
                key=[rows[0][e][k] for k in c['keys']] if c['keys'] else None, cells=cells))
        else:
            out['counts']['equal'] += 1
    for name in ('missing', 'unexpected', 'changed', 'equal'):
        out['counts'][name] = 0
    if c['mode'] == 'ordered':
        for i in range(min(len(rows[0]), len(rows[1]))):
            pair(i, i)
        for side, kind in ((0, 'missing'), (1, 'unexpected')):
            for i in range(len(rows[1-side]), len(rows[side])):
                absent(kind, side, [i])
    else:
        names = c['keys'] if c['mode'] == 'keyed' else projected
        groups_e, groups_a = groups(0, names), groups(1, names)
        if c['mode'] == 'keyed':
            _require(all(len(v) == 1 for g in (groups_e, groups_a) for v in g.values()), 'duplicate_key', 'unavailable')
        for key, ei in groups_e.items():
            ai = groups_a.get(key, [])
            matched = min(len(ei), len(ai))
            if c['mode'] == 'keyed' and matched:
                pair(ei[0], ai[0])
            else:
                out['counts']['equal'] += matched
            if len(ei) > matched:
                absent('missing', 0, ei[matched:])
        for key, ai in groups_a.items():
            matched = min(len(ai), len(groups_e.get(key, [])))
            if len(ai) > matched:
                absent('unexpected', 1, ai[matched:])
    equal = not any(out['counts'][k] for k in ('missing', 'unexpected', 'changed'))
    out.update(status='equal' if equal else 'different', equal=equal, reason=None if equal else 'value_mismatch')


_PLATFORM_TYPES = {'Строка': 'string', 'Число': 'number', 'Булево': 'boolean',
                   'Дата': 'datetime', 'УникальныйИдентификатор': 'uuid'}


def normalize_query_result(result, context, contract) -> dict:
    """Normalize a structured execute_query response, never formatted text.

    context supplies SOURCE_FIELDS except kind/status/coverage/normalization_error,
    plus response_complete: bool. Caller attests origin and data-policy handling.
    Decimal must be decoded before precision is lost (floats are rejected).
    """
    context = context if isinstance(context, Mapping) else {}
    source = {k: deepcopy(context.get(k)) for k in SOURCE_FIELDS}
    source.update(kind='execute_query', status='unknown', coverage='unknown', normalization_error=None)
    output = dict(source=source, schema=None, rows=None)
    try:
        cols, _ = _contract(contract)
        _require(isinstance(result, Mapping), 'malformed_source', 'unavailable')
        _require(type(result.get('success')) is bool, 'malformed_source', 'unavailable')
        source['status'] = 'success' if result['success'] else 'failed'
        if not result['success']:
            return output
        data, raw_schema = result.get('data'), result.get('schema')
        _require(isinstance(data, list), 'malformed_source', 'unavailable')
        limit = source['effective_limit']
        _require(type(limit) is int and limit > 0 and len(data) <= limit, 'malformed_source', 'unavailable')
        source['coverage'] = ('complete' if context.get('response_complete') is True and
            result.get('truncated', False) is False and len(data) < limit else 'unknown')
        _require(isinstance(raw_schema, Mapping) and isinstance(raw_schema.get('columns'), list), 'schema_unavailable', 'unavailable')
        schema, native = [], []
        for col in raw_schema['columns']:
            _require(isinstance(col, Mapping) and _text(col.get('name')) and isinstance(col.get('types'), list), 'schema_unavailable', 'unavailable')
            # Query schemas may include Null alongside one concrete type even
            # for a populated column. Null is distinguished by the wire value;
            # it still requires the explicit null_policy below.
            types = [t for t in col['types'] if t != 'Null']
            _require(len(types) == 1 and isinstance(types[0], str), 'ambiguous_type', 'unavailable')
            typ = types[0]
            kind = _PLATFORM_TYPES.get(typ)
            if REFERENCE.fullmatch(typ):
                kind = 'reference'
            _require(kind is not None, 'unsupported_value', 'unavailable')
            name = col['name']
            schema.append(dict(name=name, type=kind, null_policy=cols.get(name, {}).get('null_policy', 'reject')))
            native.append(typ)
        _schema(schema)
        normalized = []
        for row in data:
            _require(isinstance(row, Mapping) and set(row) == {c['name'] for c in schema}, 'malformed_source', 'unavailable')
            values = []
            for col, typ in zip(schema, native):
                value, kind = row[col['name']], col['type']
                if value is None:
                    _require(col['null_policy'] == 'wire_null', 'ambiguous_null', 'unavailable')
                    cell = dict(type='wire_null', value=None)
                else:
                    if kind == 'number':
                        _require(not isinstance(value, float), 'numeric_precision_unproven', 'unavailable')
                        _require(type(value) is int or isinstance(value, Decimal), 'malformed_source', 'unavailable')
                        value = format(value, 'f') if isinstance(value, Decimal) else str(value)
                    elif kind == 'reference':
                        _require(isinstance(value, Mapping) and value.get('_objectRef') is True and value.get('ТипОбъекта') == typ, 'malformed_source', 'unavailable')
                        value = dict(object_type=typ, id=value.get('УникальныйИдентификатор'), presentation=value.get('Представление'))
                    cell = dict(type=kind, value=value)
                    try:
                        _cell(cell, col)
                    except _Rejected:
                        raise _Rejected('malformed_source') from None
                values.append(cell)
            normalized.append(values)
        output.update(schema=schema, rows=normalized)
    except _Rejected as error:
        source['normalization_error'] = error.reason if error.reason in NORMALIZATION_ERRORS else 'malformed_source'
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        source['normalization_error'] = 'malformed_source'
    return output
