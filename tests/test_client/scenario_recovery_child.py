"""Crash boundary harness: parent kills this process after a real UI operation."""
import sys,json,time
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from onec_mcp_toolkit_proxy.scenario_context import ScenarioContextProvider
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner
folder=Path(sys.argv[1]);mode=sys.argv[2]
settings=json.loads((folder/'child.json').read_text(encoding='utf-8'))
provider=ScenarioContextProvider(settings['endpoint'],'queue1',folder/'policy.json')
def stop():
    (folder/'kill-ready').write_text('ready')
    while True:time.sleep(.1)
def transport(tool,args):
    reply=provider.transport(tool,args)
    if tool=='test_input':
        (folder/'mutation-reply.json').write_text(json.dumps(reply,ensure_ascii=False),encoding='utf-8')
        if mode=='lost-reply':stop()
    return reply
class CrashRunner(ScenarioRunner):
    def _terminal(self,reply,args,timeout):
        # The observation crash barrier needs a confirmed failed lifecycle row;
        # queue time must not turn this fixture into the separate unknown case.
        result=super()._terminal(reply,args,max(timeout,15000) if mode=='observation' else timeout)
        if mode=='saved-receipt' and args.get('action')=='text':stop()
        if mode=='observation' and result.get('status')=='failed':stop()
        return result
runner=CrashRunner(transport,provider.guard,store_path=folder/'runs.sqlite')
runner.run(settings['template'],{},provider.create())
