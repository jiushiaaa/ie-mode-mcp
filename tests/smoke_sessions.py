"""Opt-in driver crash/cleanup test. Starts IEDriver only, never Edge.

Usage: python tests/smoke_sessions.py C:/tools/IEDriverServer.exe
"""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from ie_mode_mcp import session_registry as registry


def main():
    driver_path = Path(sys.argv[1]).resolve(strict=True)
    script = '''
import os, sys
from pathlib import Path
from ie_mode_mcp import session_registry as registry
registry.registry_dir = lambda: Path(sys.argv[2])
service = registry.OwnedService(executable_path=sys.argv[1], log_output=os.devnull)
service.start()
print(service.session_id, flush=True)
input()
os._exit(0)
'''
    with TemporaryDirectory(prefix='ie-mode-ownership-') as directory:
        registry.registry_dir = lambda: Path(directory)
        child = subprocess.Popen([sys.executable, '-c', script, str(driver_path), directory],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        session_id = None
        try:
            session_id = child.stdout.readline().strip()
            assert registry.list_sessions()['sessions'][0]['state'] == 'active'
            try:
                registry.cleanup_session(session_id, False)
            except RuntimeError as error:
                assert 'Owner is alive' in str(error)
            else:
                raise AssertionError('Live owner must prevent cleanup')
            child.stdin.write('\n')
            child.stdin.flush()
            child.wait(timeout=15)  # The orphan driver can inherit pipe handles.
            record = registry.list_sessions()['sessions'][0]
            assert record['state'] == 'orphaned_driver', json.dumps(record)
            assert registry.cleanup_session(session_id)['action'] == 'terminate_owned_driver'
            assert registry.process_state(record['driver']) == 'alive'
            result = registry.cleanup_session(session_id, False)
            assert result['driver_terminated'] and registry.process_state(record['driver']) == 'gone'
            assert registry.list_sessions()['sessions'] == []
            print('PASS: real driver ownership, live-owner refusal, orphan preview and confirmed cleanup')
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
            if session_id and registry.record_path(session_id).exists():
                registry.cleanup_session(session_id, False)
            child.communicate(timeout=10)


if __name__ == '__main__':
    main()
