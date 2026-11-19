"""Isolated production proxy, without working-install configuration."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
route = sys.argv[1]
assert route in ('http', 'file')
run = root / '.local/lost-response' / route
port = {'http': 17669, 'file': 17670}[route]
os.environ.update(OPERATION_JOURNAL_DIR=str(run / 'journal'), PORT=str(port),
                  ANONYMIZATION_ENABLED='false', FILE_BRIDGE_ROOT='', FILE_BRIDGE_CHANNELS='')
if route == 'file':
    os.environ.update(FILE_BRIDGE_ROOT=str(run / 'bridge'), FILE_BRIDGE_CHANNELS='queue1')
from onec_mcp_toolkit_proxy.server import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
