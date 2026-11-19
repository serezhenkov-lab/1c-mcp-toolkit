"""Optional diagnostics: never reset platform counters or change step outcome.

Reader is a trusted callable returning {binding, values}. Binding includes the
actual client instance/epoch; values are raw cumulative platform indicators.
No attribution of shared client counters exclusively to the measured step.
"""
from copy import deepcopy
import math
import time

FIELDS=('Вызовы','Длительность','Отправлено','Принято')


class StepMetrics:
    def __init__(self, reader, *, clock=time.monotonic):
        self.reader=reader
        self.clock=clock

    def sample(self):
        try:
            value=deepcopy(self.reader())
            if not isinstance(value,dict) or not isinstance(value.get('binding'),dict):
                raise ValueError()
            if any(not isinstance(value['binding'].get(k),str) or not value['binding'][k]
                   for k in ('session_id','client_instance','counter_epoch')):
                raise ValueError()
            return value
        except Exception:
            return {'unavailable':'reader_failed'}

    def begin(self):
        return {'sample':self.sample(),'start':self.clock()}

    def finish(self, token, *, run_id, step_execution_id, operation_id, session_id):
        end=self.clock()
        after=self.sample();before=token['sample']
        reason=None
        if 'unavailable' in before or 'unavailable' in after:reason='reader_failed'
        elif before['binding']!=after['binding']:reason='counter_binding_changed'
        elif before['binding']['session_id']!=session_id:reason='session_mismatch'
        result=dict(run_id=run_id,step_execution_id=step_execution_id,operation_id=operation_id,
            source='ТестируемоеПриложение.ПолучитьНакопленныеПоказателиПроизводительности(Ложь)',
            attribution='shared_client_interval_not_exclusive',aggregation='do_not_sum',
            start=token['start'],end=end,wall_seconds=max(0,end-token['start']),
            clock='collector_monotonic',boundary='after_guard_before_dispatch_to_terminal_reply',
            samples={'before':before,'after':after},indicators={})
        for key in FIELDS:
            a=before.get('values',{}).get(key);b=after.get('values',{}).get(key)
            unavailable=reason
            if not unavailable and any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (a,b)):
                unavailable='counter_unavailable'
            if not unavailable and b<a:unavailable='counter_decreased'
            result['indicators'][key]=dict(available=not unavailable,value=None if unavailable else b-a,
                reason=unavailable,unit='count' if key=='Вызовы' else 'platform_native_unit_unverified')
        return result


def interval_union_seconds(records):
    """Union only within one collector clock domain, never sum counter deltas.
    Caller must supply records from the same collector process/clock domain.
    """
    spans=sorted((r['start'],r['end']) for r in records)
    total=0;last=None
    for start,end in spans:
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (start,end)) or end<start:
            raise ValueError('invalid_interval')
        if last is None or start>last:total+=end-start;last=end
        elif end>last:total+=end-last;last=end
    return total
