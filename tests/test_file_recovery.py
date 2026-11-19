import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from onec_mcp_toolkit_proxy.file_recovery import recover_channel, RecoveryBlocked, ExecutorFence
from onec_mcp_toolkit_proxy.operation_journal import OperationJournal
from onec_mcp_toolkit_proxy.file_transport import write_json


class Fence:
    def __init__(self,path):self.path=path;self.closed=False
    def __enter__(self):return self
    def __exit__(self,*a):self.closed=True


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.channel=self.root/'channel';self.channel.mkdir()
        self.session=str(uuid.uuid4());self.previous=self.channel/self.session;self.previous.mkdir()
        self.pointer=dict(version=1,channel='channel',session=self.session)
        write_json(self.channel/'current.json',self.pointer)
        write_json(self.previous/'session.json',dict(version=1,channel='channel'))
        journal=OperationJournal(self.root/'journal')
        self.identifier,_=journal.reserve('channel','same-key','test_action',{'action':'click'})
        journal.transition(self.identifier,'running');journal.close()
        self.store=OperationJournal(self.root/'journal')
        self.queue=SimpleNamespace(operation_store=lambda:self.store)
        self.running=self.previous/(self.identifier+'.running');self.running.write_text('{}')
        write_json(self.previous/(self.identifier+'.fence.json'),dict(version=1,channel='channel',session=self.session,id=self.identifier))

    def tearDown(self):self.store.close();self.temp.cleanup()

    def recover(self):return recover_channel(self.channel,self.queue,fence_factory=Fence)

    def test_recovered_key_unknown_and_files_preserved(self):
        fence=self.recover()
        self.assertFalse(fence.closed)
        self.assertFalse((self.previous/'session.json').exists())
        self.assertTrue(self.running.exists())
        self.assertEqual(json.loads((self.channel/'current.json').read_text()),self.pointer)
        self.assertEqual(self.store.get('channel',self.identifier)['state'],'unknown')
        ident,fresh=self.store.reserve('channel','same-key','test_action',{'action':'click'})
        self.assertEqual(ident,self.identifier);self.assertFalse(fresh)
        fence.__exit__()

    def test_crash_before_new_pointer_idempotent(self):
        self.recover().__exit__();self.recover().__exit__()
        self.assertTrue(self.running.exists())

    def test_busy_revokes_without_publishing(self):
        class Busy(Fence):
            def __enter__(self):raise RecoveryBlocked('executor_busy')
        with self.assertRaisesRegex(RecoveryBlocked,'executor_busy'):
            recover_channel(self.channel,self.queue,fence_factory=Busy)
        self.assertFalse((self.previous/'session.json').exists())
        self.assertTrue(self.running.exists())
        self.assertEqual(json.loads((self.channel/'current.json').read_text()),self.pointer)

    def test_legacy_request_stays_blocked(self):
        (self.previous/(self.identifier+'.fence.json')).unlink()
        with self.assertRaisesRegex(RecoveryBlocked,'legacy_unfenced_request'):self.recover()
        self.assertTrue((self.previous/'session.json').exists())

    def test_wrong_marker_channel(self):
        write_json(self.previous/(self.identifier+'.fence.json'),dict(version=1,channel='other',session=self.session,id=self.identifier))
        with self.assertRaisesRegex(RecoveryBlocked,'invalid_executor_fence'):self.recover()

    def test_absent_journal_identity_blocks(self):
        self.queue.operation_store=lambda:SimpleNamespace(get=lambda *a:(_ for _ in ()).throw(ValueError('missing')))
        with self.assertRaises(ValueError):self.recover()
        self.assertTrue((self.previous/'session.json').exists())

    def test_unclaimed_request_blocks(self):
        (self.previous/(str(uuid.uuid4())+'.request.json')).write_text('{}')
        with self.assertRaisesRegex(RecoveryBlocked,'legacy_unfenced_request'):self.recover()

    def test_claim_between_directory_scans_is_not_missed(self):
        request = self.previous / (self.identifier + '.request.json')
        self.running.rename(request)
        (self.previous / (self.identifier + '.fence.json')).unlink()
        original_glob = Path.glob
        first_scan = True

        def concurrent_claim(path, pattern):
            nonlocal first_scan
            found = list(original_glob(path, pattern))
            if first_scan:
                first_scan = False
                request.rename(self.running)
            return iter(found)

        with patch.object(Path, 'glob', concurrent_claim):
            with self.assertRaisesRegex(RecoveryBlocked, 'legacy_unfenced_request'):
                self.recover()
        self.assertEqual(json.loads((self.channel / 'current.json').read_text()), self.pointer)

    def test_windows_fence_excludes_second_writer(self):
        import os
        if os.name!='nt':self.skipTest('Windows sharing semantics')
        with ExecutorFence(self.channel/'executor.lock'):
            with self.assertRaisesRegex(RecoveryBlocked,'executor_busy'):
                with ExecutorFence(self.channel/'executor.lock'):pass
        with ExecutorFence(self.channel/'executor.lock'):pass


if __name__=='__main__':unittest.main()
