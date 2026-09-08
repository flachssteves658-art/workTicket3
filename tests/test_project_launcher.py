"""Exercise ownership, repeat-start, foreign-port and lifecycle behaviour."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('launcher_under_test', ROOT / 'scripts/project_launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@unittest.skipUnless(os.name == 'nt', 'Windows process identities')
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='workticket-launcher-test-')
        launcher.RUNTIME = Path(self.folder.name)
        launcher.STATE = launcher.RUNTIME / 'processes.json'
        self.state = {}
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.service = {'name': 'test-service', 'port': port, 'routes': ['/launcher-test'],
                        'cwd': str(ROOT), 'env': launcher.process_env(sys.executable, ROOT),
                        'command': [sys.executable, '-u', str(ROOT / 'tests/fake_launcher_service.py'), str(port)]}

    def tearDown(self):
        for name, record in self.state.items():
            launcher.stop_record(name, record)
        self.folder.cleanup()

    def test_repeat_start_stop_and_pid_reuse_protection(self):
        self.assertTrue(launcher.start_service(self.service, self.state, 10))
        record = self.state['test-service']
        self.assertTrue(launcher.owned_alive(record))
        saved_pid = record['identity']['pid']
        self.assertFalse(launcher.start_service(self.service, self.state, 10))
        self.assertEqual(saved_pid, self.state['test-service']['identity']['pid'])
        stale = {**record, 'identity': {**record['identity'], 'created': 0}}
        self.assertFalse(launcher.owned_alive(stale))
        self.assertTrue(launcher.stop_record('wrong-identity', stale))
        self.assertTrue(launcher.owned_alive(record))
        self.assertTrue(launcher.stop_record('test-service', record))
        self.assertFalse(launcher.owned_alive(record))

    def test_external_service_is_reused_and_not_stopped(self):
        launcher.start_service(self.service, self.state, 10)
        own = self.state['test-service']
        external_state = {}
        self.assertFalse(launcher.start_service(self.service, external_state, 10))
        self.assertTrue(external_state['test-service']['external'])
        launcher.stop_record('external', external_state['test-service'])
        self.assertTrue(launcher.owned_alive(own))

    def test_foreign_port_is_rejected(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', self.service['port']))
            sock.listen()
            with self.assertRaisesRegex(RuntimeError, '被其他程序占用'):
                launcher.start_service(self.service, self.state, 5)
        self.assertEqual(self.state, {})

    def test_early_exit_keeps_owned_identity_for_cleanup(self):
        self.service['command'] = [sys.executable, '-c', 'import time; time.sleep(0.4); raise SystemExit(7)']
        with self.assertRaises(RuntimeError):
            launcher.start_service(self.service, self.state, 5)
        for record in self.state.values():
            self.assertTrue(launcher.stop_record('failed', record))

    def test_controller_lock_prevents_overlap(self):
        with launcher.lock():
            with self.assertRaisesRegex(RuntimeError, '另一个启动'):
                with launcher.lock():
                    self.fail('second controller entered')


if __name__ == '__main__':
    unittest.main(verbosity=2)
