"""Test-only delay after a successful native reply; production clocks are untouched."""
from pathlib import Path
import sys,json,time
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
folder=Path(sys.argv.pop(1)).resolve()
assert folder.is_relative_to(root/'.local')
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner
original=ScenarioRunner._terminal
paused=False

def delayed(self,reply,arguments,timeout_ms):
 global paused
 result=original(self,reply,arguments,timeout_ms)
 if not paused and arguments.get('action')=='text' and result.get('status')=='succeeded':
  paused=True
  context=next(iter(self._runs.values()))['context']
  (folder/'context-before-delay.json').write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf-8')
  (folder/'native-before-delay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  deadline=datetime.fromisoformat(context['expires_at']).timestamp()+1
  started=datetime.now(timezone.utc)
  (folder/'delay-start.json').write_text(json.dumps(dict(started_at=started.isoformat(),until=deadline,operation_id=result['operation_id'])),encoding='utf-8')
  while time.time()<deadline:time.sleep(min(.25,max(.01,deadline-time.time())))
  (folder/'delay-end.json').write_text(json.dumps(dict(ended_at=datetime.now(timezone.utc).isoformat(),seconds=time.time()-started.timestamp())),encoding='utf-8')
 return result

ScenarioRunner._terminal=delayed
from onec_mcp_toolkit_proxy.scenario_context import main
main()
