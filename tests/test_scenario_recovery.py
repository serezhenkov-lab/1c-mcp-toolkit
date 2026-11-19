from copy import deepcopy
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from test_scenario_runner import scenario, context_for, Transport, guard
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner
from onec_mcp_toolkit_proxy.scenario_store import RunStore
import sqlite3


class LostProcess(BaseException):pass

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'runs.sqlite'
        self.t=scenario();self.p={'marker':'once'};self.c=context_for(self.t,self.p)
        self.tr=Transport()

    def crash(self, receipt=True):
        runner=ScenarioRunner(self.tr,guard,store_path=self.path)
        if receipt:
            runner._terminal=lambda *args: (_ for _ in ()).throw(LostProcess())
        else:
            def lost(tool,args):
                self.tr(tool,args)
                raise LostProcess()
            runner._transport=lost
        with self.assertRaises(LostProcess):runner.run(self.t,self.p,self.c)
        with closing(sqlite3.connect(self.path)) as db:return db.execute('SELECT id FROM runs').fetchone()[0]

    def recover(self,rid,**kwargs):
        return ScenarioRunner(self.tr,guard,store_path=self.path).recover(rid,self.c,**kwargs)

    def test_receipt_recovery_and_explicit_resume_once(self):
        rid=self.crash();r=self.recover(rid)
        self.assertEqual(r['status'],'recovered');self.assertEqual(len(self.tr.requests),1)
        r=self.recover(rid,resume=True)
        self.assertEqual(r['status'],'succeeded');self.assertEqual(len(self.tr.requests),2)
        self.recover(rid,resume=True)
        self.assertEqual(len(self.tr.requests),2);self.assertEqual(self.tr.mutations,1)

    def test_response_lost_never_replays(self):
        rid=self.crash(False)
        for _ in range(2):self.assertEqual(self.recover(rid,resume=True)['status'],'unknown')
        self.assertEqual(self.tr.mutations,1);self.assertEqual(len(self.tr.requests),1)

    def test_changed_binding_blocks(self):
        rid=self.crash();self.c['session_id']='new'
        self.assertEqual(self.recover(rid,resume=True)['reason'],'recovery_binding_mismatch')
        self.assertEqual(len(self.tr.requests),1)

    def test_retention_and_wrong_identity_block(self):
        rid=self.crash();key=next(iter(self.tr.ops));original=deepcopy(self.tr.ops[key])
        for value in ({},dict(original,request_id='foreign'),dict(original,status='unknown'),dict(original,status='running')):
            self.tr.ops[key]=value
            self.assertNotEqual(self.recover(rid,resume=True)['status'],'succeeded')
        self.assertEqual(len(self.tr.requests),1)

    def test_guard_stops_new_step(self):
        rid=self.crash()
        r=ScenarioRunner(self.tr,lambda *_:{'allowed':False},store_path=self.path).recover(rid,self.c,resume=True)
        self.assertEqual(r['status'],'partial');self.assertEqual(len(self.tr.requests),1)

    def test_unknown_history_is_preserved(self):
        rid=self.crash();store=RunStore(self.path);state=store.load(rid)
        state['output']['steps'][0]['status']='unknown';store.save(state)
        r=self.recover(rid,resume=True)
        self.assertEqual(r['status'],'partial');self.assertEqual(r['steps'][0]['status'],'unknown')
        self.assertEqual(r['steps'][0]['reconciliation']['status'],'succeeded')
        self.assertEqual(self.tr.mutations,1)

    def test_concurrent_owner_excluded_and_lock_released(self):
        store=RunStore(self.path)
        with store.locked():
            with self.assertRaises(OSError):
                with RunStore(self.path).locked():pass
        with store.locked():pass

    def test_preflight_policy_change_prevents_dispatch(self):
        rid=self.crash();self.c['scope_digests']=[]
        self.assertEqual(self.recover(rid,resume=True)['reason'],'recovery_preflight_failed')
        self.assertEqual(self.tr.mutations,1)

    def test_store_failure_prevents_first_dispatch(self):
        runner=ScenarioRunner(self.tr,guard,store_path=self.path)
        def fail(_):raise OSError('disk unavailable')
        runner._store.save=fail
        with self.assertRaises(OSError):runner.run(self.t,self.p,self.c)
        self.assertEqual(self.tr.requests,[])

    def test_completed_run_never_dispatches_again(self):
        runner=ScenarioRunner(self.tr,guard,store_path=self.path)
        original=runner.run(self.t,self.p,self.c)
        recovered=self.recover(original['run_id'],resume=True)
        self.assertEqual(recovered['status'],'succeeded')
        self.assertEqual(len(self.tr.requests),2);self.assertEqual(self.tr.mutations,1)

    def test_discover_interrupted_run_without_parameters(self):
        rid=self.crash()
        listed=RunStore(self.path).list_runs()
        self.assertEqual(listed[0]['run_id'],rid)
        self.assertEqual(listed[0]['steps'][0]['status'],'dispatching')
        self.assertNotIn('parameters',listed[0]);self.assertNotIn('context',listed[0])

if __name__=='__main__':unittest.main()
