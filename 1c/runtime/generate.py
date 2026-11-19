"""Synchronize embedded lifecycle fragments and public schemas; never edit legacy generated blocks."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from onec_mcp_toolkit_proxy.test_client_contract import INPUT_SCHEMAS
from onec_mcp_toolkit_proxy.approval_control import SET_APPROVAL_MODE_SCHEMA

def render():
    schema = json.dumps(INPUT_SCHEMAS, ensure_ascii=False, separators=(',', ':'))
    # Split JSON into manageable BSL string lines without changing its contents.
    parts = [schema[i:i+1800].replace('"', '""') for i in range(0, len(schema), 1800)]
    text = '&НаКлиенте\nФункция СхемыТестированияLifecycle()\n\tВозврат ПрочитатьJSON2(\n'
    text += ' +\n'.join('\t\t"' + part + '"' for part in parts)
    text += ');\nКонецФункции\n'
    approval_schema = json.dumps(SET_APPROVAL_MODE_SCHEMA, ensure_ascii=False, separators=(',', ':')).replace('"', '""')
    text += '&НаКлиенте\nФункция СхемаУправленияРазрешениямиMCP()\n\tВозврат ПрочитатьJSON2("' + approval_schema + '");\nКонецФункции\n'
    for name in ('embedded_lifecycle.bsl', 'embedded_compaction.bsl', 'embedded_test_adapter.bsl', 'local_test_profile.bsl', 'approval_control.bsl', 'test_client_log.bsl'):
        text += '\n' + (Path(__file__).parent / name).read_text(encoding='utf-8-sig')
    return '\n// BEGIN EMBEDDED LIFECYCLE\n' + text.rstrip() + '\n// END EMBEDDED LIFECYCLE\n'

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / '1c/MCPToolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
    old = path.read_text(encoding='utf-8-sig')
    new = old.split('\n// BEGIN EMBEDDED LIFECYCLE')[0].rstrip() + '\n' + render()
    if args.check:
        assert old == new, 'Run 1c/runtime/generate.py'
    else:
        path.write_text(new, encoding='utf-8-sig')
