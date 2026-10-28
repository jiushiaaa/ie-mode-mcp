from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
from uuid import uuid4

import pytest

from ie_mode_mcp import session_registry as registry


@pytest.fixture
def record(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'registry_dir', lambda: tmp_path)
    session_id = str(uuid4())
    data = {'session_id': session_id,
            'owner': {'pid': 1234, 'created': 111, 'path': str(tmp_path / 'python.exe')},
            'driver': {'pid': 5678, 'created': 222, 'path': str(tmp_path / 'IEDriverServer.exe')}}
    registry.record_path(session_id).write_text(json.dumps(data), encoding='utf-8')
    return data


@pytest.mark.parametrize('owner,driver,expected', [
    ('alive', 'alive', 'active'), ('gone', 'alive', 'orphaned_driver'),
    ('gone', 'gone', 'finished'), ('unknown', 'alive', 'unknown'),
])
def test_registry_classifies_without_browser_contact(record, monkeypatch, owner, driver, expected):
    monkeypatch.setattr(registry.sys, 'platform', 'win32')
    monkeypatch.setattr(registry, 'process_state', lambda identity: owner if identity == record['owner'] else driver)
    assert registry.list_sessions()['sessions'][0]['state'] == expected


@pytest.mark.parametrize('state', ['alive', 'unknown'])
def test_cleanup_refuses_live_or_unverifiable_owner(record, monkeypatch, state):
    monkeypatch.setattr(registry, 'process_state', lambda identity: state)
    opened = Mock()
    monkeypatch.setattr(registry, 'process_handle', opened)
    with pytest.raises(RuntimeError, match='refused'):
        registry.cleanup_session(record['session_id'], False)
    opened.assert_not_called()
    assert registry.record_path(record['session_id']).exists()


@pytest.mark.parametrize('dry_run,reused', [(True, False), (False, False), (False, True)])
def test_cleanup_checks_identity_on_same_termination_handle(record, monkeypatch, dry_run, reused):
    monkeypatch.setattr(registry, 'process_state', lambda identity: 'gone')
    api = Mock()
    api.WaitForSingleObject.side_effect = [258, 0]
    api.TerminateProcess.return_value = True
    handle = object()
    @contextmanager
    def opened(pid, terminate=False):
        assert pid == record['driver']['pid'] and terminate == (not dry_run)
        yield api, handle
    monkeypatch.setattr(registry, 'process_handle', opened)
    actual = {**record['driver'], 'created': 999} if reused else record['driver']
    identity = Mock(return_value=actual)
    monkeypatch.setattr(registry, 'identity_from_handle', identity)
    result = registry.cleanup_session(record['session_id'], dry_run)
    identity.assert_called_once_with(api, handle, record['driver']['pid'])
    if not dry_run and not reused:
        api.TerminateProcess.assert_called_once_with(handle, 1)
        assert result['driver_terminated']
    else:
        api.TerminateProcess.assert_not_called()
    assert registry.record_path(record['session_id']).exists() == dry_run


def test_failed_termination_preserves_record(record, monkeypatch):
    monkeypatch.setattr(registry, 'process_state', lambda identity: 'gone')
    api = Mock()
    api.WaitForSingleObject.return_value = 258
    @contextmanager
    def opened(*args, **kwargs):
        yield api, 1
    monkeypatch.setattr(registry, 'process_handle', opened)
    monkeypatch.setattr(registry, 'identity_from_handle', lambda *args: record['driver'])
    with pytest.raises(RuntimeError, match='not confirmed'):
        registry.cleanup_session(record['session_id'], False)
    assert registry.record_path(record['session_id']).exists()


def test_cleanup_rejects_non_driver_and_path_traversal(record):
    for value in ('../other', str(uuid4()) + '/file'):
        with pytest.raises(ValueError):
            registry.record_path(value)
    record['driver']['path'] = str(Path(record['driver']['path']).with_name('msedge.exe'))
    path = registry.record_path(record['session_id'])
    path.write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(ValueError, match='IEDriver'):
        registry.cleanup_session(record['session_id'], False)


def test_unknown_process_is_not_assumed_dead(monkeypatch):
    monkeypatch.setattr(registry, 'process_identity', Mock(side_effect=PermissionError()))
    assert registry.process_state({'pid': 5}) == 'unknown'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows process handles')
def test_current_process_identity_and_missing_pid():
    identity = registry.process_identity(os.getpid())
    assert identity['pid'] == os.getpid() and identity['created'] > 0
    assert Path(identity['path']).name.lower() == Path(sys.executable).name.lower()
    assert registry.process_state(identity) == 'alive'
    assert registry.process_state({**identity, 'created': 1}) == 'gone'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows named mutex')
def test_separate_process_cannot_enter_busy_desktop_and_crash_releases_lock(monkeypatch):
    # A unique kernel object avoids colliding with real user operations.
    name = 'Local\\ie-mode-mcp-test-' + str(uuid4())
    monkeypatch.setattr(registry, 'DESKTOP_MUTEX_NAME', name)
    script = ('import os\nfrom ie_mode_mcp import session_registry as registry\n'
              + 'registry.DESKTOP_MUTEX_NAME = ' + repr(name) + '\n'
              + 'with registry.desktop_lease():\n print(os.getpid(), flush=True)\n input()\n')
    child = subprocess.Popen([sys.executable, '-c', script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        holder_pid = int(child.stdout.readline().strip())
        with pytest.raises(RuntimeError, match='Another ie-mode-mcp'):
            with registry.desktop_lease():
                pytest.fail('Concurrent entry must not execute')
        # Windows venv python.exe can be a launcher: terminate the process
        # actually holding the mutex, not just its launcher Popen PID.
        with registry.process_handle(holder_pid, terminate=True) as (api, handle):
            assert handle and api.TerminateProcess(handle, 1)
            assert api.WaitForSingleObject(handle, 10000) == 0
        child.wait(timeout=10)
        with registry.desktop_lease():
            with registry.desktop_lease():  # nested Browser calls on the same thread
                pass
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)


def test_service_registers_before_webdriver_session_and_removes_only_dead_driver(record, monkeypatch):
    monkeypatch.setattr(registry.Service, 'start', lambda service: setattr(service, 'process', Mock(pid=5678)))
    monkeypatch.setattr(registry.Service, 'stop', lambda service: None)
    registered = Mock(return_value=record['session_id'])
    monkeypatch.setattr(registry, 'register_driver', registered)
    monkeypatch.setattr(registry, 'process_state', lambda identity: 'unknown')
    service = registry.OwnedService()
    service.start()
    registered.assert_called_once_with(5678)
    service.stop()
    assert registry.record_path(record['session_id']).exists()
    monkeypatch.setattr(registry, 'process_state', lambda identity: 'gone')
    service.stop()
    assert not registry.record_path(record['session_id']).exists()
