from copy import deepcopy
from contextlib import closing
import sqlite3
import unittest
import test_scenario_recovery as fixture
from test_scenario_recovery import LostProcess
from test_scenario_runner import context_for,guard
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner


class ObservationRecoveryTests(unittest.TestCase):
    recover=fixture.RecoveryTests.recover
    def setUp(self):
        fixture.RecoveryTests.setUp(self)
        fail=deepcopy(self.t['steps'][1]);fail.update(step_id='failed_read',on_error='continue_observation')
        self.t['steps']=[fail,self.t['steps'][0],self.t['steps'][1]]
        self.c=context_for(self.t,self.p)
        original=self.tr.__call__
        def transport(tool,args):
            reply=original(tool,args)
            if tool!='test_session' and args['request_id']==self.first_request:
                reply.update(status=self.failure_status,error={'code':self.failure_code})
                self.tr.ops[args['request_id']]=reply
            return reply
        self.first_request=None;self.failure_status='failed';self.failure_code='expectation_failed'
        def capture(tool,args):
            if tool!='test_session' and self.first_request is None:self.first_request=args['request_id']
            return transport(tool,args)
        self.transport=capture

    def start_crashed(self):
        runner=ScenarioRunner(self.transport,guard,store_path=self.path)
        runner._terminal=lambda *args: (_ for _ in ()).throw(LostProcess())
        with self.assertRaises(LostProcess):runner.run(self.t,self.p,self.c)
        with closing(sqlite3.connect(self.path)) as db:return db.execute('SELECT id FROM runs').fetchone()[0]

    def test_resume_observations_skips_mutation_and_preserves_failure(self):
        rid=self.start_crashed();r=self.recover(rid,resume=True)
        self.assertEqual(r['status'],'partial');self.assertTrue(r['observation_only'])
        self.assertEqual([s['status'] for s in r['steps']],['failed','skipped','succeeded'])
        self.assertEqual(self.tr.mutations,0);self.assertEqual(len(self.tr.requests),2)
        self.assertEqual(self.recover(rid,resume=True)['status'],'partial')
        self.assertEqual(len(self.tr.requests),2)

    def test_stop_policy_does_not_become_unknown(self):
        self.t['steps'][0]['on_error']='stop';rid=self.start_crashed()
        r=self.recover(rid,resume=True)
        self.assertEqual(r['status'],'failed');self.assertEqual(len(self.tr.requests),1)

    def test_permission_failure_never_continues(self):
        self.failure_code='permission_denied';rid=self.start_crashed()
        self.assertEqual(self.recover(rid,resume=True)['reason'],'step_policy_stopped')
        self.assertEqual(len(self.tr.requests),1)

    def test_unknown_never_enables_observation_policy(self):
        self.failure_status='unknown';rid=self.start_crashed()
        self.assertEqual(self.recover(rid,resume=True)['status'],'unknown')
        self.assertEqual(len(self.tr.requests),1)

    def test_second_crash_after_persisted_skip(self):
        rid=self.start_crashed();runner=ScenarioRunner(self.tr,guard,store_path=self.path)
        save=runner._store.save
        def crash_after_skip(state):
            save(state)
            if state['output']['steps'][-1]['status']=='skipped':raise LostProcess()
        runner._store.save=crash_after_skip
        with self.assertRaises(LostProcess):runner.recover(rid,self.c,resume=True)
        r=self.recover(rid,resume=True)
        self.assertEqual([s['status'] for s in r['steps']],['failed','skipped','succeeded'])
        self.assertEqual(self.tr.mutations,0);self.assertEqual(len(self.tr.requests),2)

