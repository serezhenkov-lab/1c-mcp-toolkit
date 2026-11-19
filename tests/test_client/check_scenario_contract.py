"""Check 11.1 artifacts against JSON Schema and existing public request shapes.

This is not runtime preflight: context/capability/error-policy expectations in
the examples remain a documented manual contract review for 11.3.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from onec_mcp_toolkit_proxy.test_client_contract import valid_request


def main():
    change = ROOT / 'openspec/changes/upravlenie-test-klientom'
    schema_path = change / 'contracts/scenario-v1.schema.json'
    examples_path = change / 'contracts/scenario-v1.examples.json'
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    examples = json.loads(examples_path.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    checks = []
    for case in examples['cases']:
        template = case['template']
        actual = validator.is_valid(template)
        assert actual == case['schema_valid'], case['name']
        public = None
        if case['public_requests_valid'] is not None:
            def resolve(value):
                if isinstance(value, dict):
                    if set(value) == {'$param'}:
                        return deepcopy(case['parameters'][value['$param']])
                    return {k: resolve(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [resolve(v) for v in value]
                return value
            public = all(valid_request(step['tool'], dict(resolve(step['arguments']),
                request_id='shape-check-only', session_id='shape-check-only',
                timeout_ms=step['timeout_ms'])) for step in template['steps'])
            assert public == case['public_requests_valid'], case['name']
        checks.append(dict(name=case['name'], schema_valid=actual,
                           public_requests_valid=public, ok=True))
    report = dict(task='TASK-021/11.1', schema_cases=len(checks),
        public_shape_cases=sum(c['public_requests_valid'] is not None for c in checks),
        checks=checks, semantic_preflight='manual review of rules, not runtime execution',
        runtime_preflight_implemented=False, commands_dispatched=0,
        files_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (schema_path, examples_path, ROOT/'onec_mcp_toolkit_proxy/test_client_contract.py')})
    (change/'evidence/scenario-contract-review.json').write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(schema_cases=report['schema_cases'],
                         public_shape_cases=report['public_shape_cases'],result='OK')))


if __name__ == '__main__':
    main()
