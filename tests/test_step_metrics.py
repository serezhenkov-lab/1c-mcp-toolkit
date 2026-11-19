from copy import deepcopy
import unittest
from onec_mcp_toolkit_proxy.step_metrics import StepMetrics,interval_union_seconds,FIELDS
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner
from test_scenario_runner import scenario,context_for,guard,Transport


def sample(value=10):
    return dict(binding=dict(session_id='session',client_instance='pid:created',counter_epoch='epoch'),
                values={k:value for k in FIELDS})


class MetricTests(unittest.TestCase):
    def measure(self,a,b):
        values=iter([a,b]);clock=iter([1,4])
        m=StepMetrics(lambda:next(values),clock=lambda:next(clock))
        return m.finish(m.begin(),run_id='run',step_execution_id='step',operation_id='op',session_id='session')

    def test_delta_and_boundaries(self):
        r=self.measure(sample(),sample(13))
        self.assertEqual(r['wall_seconds'],3)
        self.assertTrue(all(v['value']==3 for v in r['indicators'].values()))
        self.assertEqual(r['operation_id'],'op');self.assertEqual(r['aggregation'],'do_not_sum')

    def test_missing_not_zero(self):
        b=sample();del b['values']['Вызовы']
        self.assertIsNone(self.measure(sample(),b)['indicators']['Вызовы']['value'])

    def test_decrease_not_negative_delta(self):
        self.assertEqual(self.measure(sample(),sample(0))['indicators']['Вызовы']['reason'],'counter_decreased')

    def test_other_client_or_epoch(self):
        for key in ('client_instance','counter_epoch','session_id'):
            b=sample();b['binding'][key]='other'
            self.assertFalse(self.measure(sample(),b)['indicators']['Вызовы']['available'])

    def test_invalid_values(self):
        for invalid in (True,float('nan'),-1,'10',None):
            b=sample();b['values']['Вызовы']=invalid
            self.assertFalse(self.measure(sample(),b)['indicators']['Вызовы']['available'])

    def test_read_error_preserves_successful_step(self):
        def broken():raise RuntimeError('private')
        t=scenario();p={'marker':'metric'}
        r=ScenarioRunner(Transport(),guard,metrics=StepMetrics(broken)).run(t,p,context_for(t,p))
        self.assertEqual(r['status'],'succeeded')
        self.assertEqual(r['steps'][0]['metrics']['indicators']['Вызовы']['reason'],'reader_failed')
        self.assertNotIn('private',str(r))

    def test_diagnostic_exception_preserves_outcome(self):
        class Broken:
            def begin(self):raise RuntimeError()
            def finish(self,*a,**kw):raise RuntimeError()
        t=scenario();p={'marker':'metric'}
        r=ScenarioRunner(Transport(),guard,metrics=Broken()).run(t,p,context_for(t,p))
        self.assertEqual(r['status'],'succeeded')
        self.assertEqual(r['steps'][0]['metrics']['reason'],'diagnostics_failed')

    def test_nested_parallel_union(self):
        r=[{'start':0,'end':10},{'start':2,'end':4},{'start':8,'end':14},{'start':20,'end':22}]
        self.assertEqual(interval_union_seconds(r),16)

    def test_failed_outcome_not_replaced(self):
        t=scenario();p={'marker':'metric'};tr=Transport()
        tr.fail=lambda *a:dict(status='failed',error={'code':'test_failure'})
        r=ScenarioRunner(tr,guard,metrics=StepMetrics(lambda:sample())).run(t,p,context_for(t,p))
        self.assertEqual(r['status'],'failed');self.assertEqual(r['steps'][0]['result']['error']['code'],'test_failure')

    def test_retry_does_not_collect_or_reset_counters(self):
        reads=[]
        def reader():reads.append(1);return sample(len(reads))
        t=scenario();p={'marker':'metric'}
        runner=ScenarioRunner(Transport(),guard,metrics=StepMetrics(reader))
        r=runner.run(t,p,context_for(t,p));count=len(reads)
        runner.retry_delivery(r['run_id'],'input',plan_digest=r['preflight']['plan_digest'])
        self.assertEqual(len(reads),count)


if __name__=='__main__':unittest.main()
