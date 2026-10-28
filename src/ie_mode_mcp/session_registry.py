"""Windows process identity and cooperative desktop ownership.

Registry entries contain process metadata only. Never enumerate or kill Edge:
its process tree and cookies can be shared with windows outside our session.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from functools import wraps
import json
import os
from pathlib import Path
import sys
from uuid import UUID, uuid4

from selenium.webdriver.ie.service import Service

DESKTOP_MUTEX_NAME = r'Local\ie-mode-mcp-desktop-v1'


def kernel():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateMutexW': ([ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'ReleaseMutex': ([wintypes.HANDLE], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        'GetProcessTimes': ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
        'QueryFullProcessImageNameW': ([wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                       ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        'TerminateProcess': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(api, name)
        fn.argtypes, fn.restype = args, result
    return api


@contextmanager
def desktop_lease():
    # Allows non-Windows package inspection/tests, not browser execution.
    if sys.platform != 'win32':
        yield
        return
    api = kernel()
    handle = api.CreateMutexW(None, False, DESKTOP_MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    acquired = False
    try:
        state = api.WaitForSingleObject(handle, 0)
        if state == 258:
            raise RuntimeError('Another ie-mode-mcp process is using this desktop. No action was performed; inspect its status before trying again.')
        if state not in (0, 128):  # acquired or abandoned by a terminated owner
            raise ctypes.WinError(ctypes.get_last_error())
        acquired = True
        yield
    finally:
        if acquired:
            api.ReleaseMutex(handle)
        api.CloseHandle(handle)


def desktop_operation(fn):
    @wraps(fn)
    def guarded(self, *args, **kwargs):
        with self.lock, desktop_lease():
            return fn(self, *args, **kwargs)
    return guarded


def identity_from_handle(api, handle, pid):
    created, exited, kern, user = (wintypes.FILETIME() for _ in range(4))
    if not api.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                               ctypes.byref(kern), ctypes.byref(user)):
        raise ctypes.WinError(ctypes.get_last_error())
    size = wintypes.DWORD(32768)
    path = ctypes.create_unicode_buffer(size.value)
    if not api.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'pid': pid, 'created': (created.dwHighDateTime << 32) | created.dwLowDateTime,
            'path': os.path.normcase(path.value)}


@contextmanager
def process_handle(pid, terminate=False):
    if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF:
        raise ValueError('Invalid process ID.')
    api = kernel()
    handle = api.OpenProcess(0x1000 | 0x100000 | (1 if terminate else 0), False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # no such PID
            yield api, None
            return
        raise ctypes.WinError(error)
    try:
        yield api, handle
    finally:
        api.CloseHandle(handle)


def process_identity(pid):
    with process_handle(pid) as (api, handle):
        if handle is None:
            return None
        state = api.WaitForSingleObject(handle, 0)
        if state == 0:
            return None
        if state != 258:
            raise ctypes.WinError(ctypes.get_last_error())
        return identity_from_handle(api, handle, pid)


def process_state(expected):
    try:
        actual = process_identity(expected['pid'])
        return 'alive' if actual == expected else 'gone'
    except (OSError, KeyError, ValueError, TypeError):
        return 'unknown'


def registry_dir():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'ie-mode-mcp' / 'sessions'


def record_path(session_id):
    if not isinstance(session_id, str) or str(UUID(session_id)) != session_id:
        raise ValueError('Use an exact session_id returned by browser_sessions.')
    return registry_dir() / (session_id + '.json')


def register_driver(pid):
    owner, driver = process_identity(os.getpid()), process_identity(pid)
    if not owner or not driver or Path(driver['path']).name.lower() != 'iedriverserver.exe':
        raise RuntimeError('Cannot establish IEDriver ownership.')
    session_id = str(uuid4())
    target = record_path(session_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps({'session_id': session_id, 'owner': owner, 'driver': driver}), encoding='utf-8')
    temporary.replace(target)
    return session_id


def read_record(path):
    record = json.loads(path.read_text(encoding='utf-8'))
    if record_path(record['session_id']) != path:
        raise ValueError('Session record filename mismatch.')
    for key in ('owner', 'driver'):
        item = record[key]
        if (type(item['pid']) is not int or not 0 < item['pid'] <= 0xFFFFFFFF
                or type(item['created']) is not int or item['created'] <= 0
                or not isinstance(item['path'], str) or not Path(item['path']).is_absolute()):
            raise ValueError('Invalid process identity.')
    if Path(record['driver']['path']).name.lower() != 'iedriverserver.exe':
        raise ValueError('Not an IEDriver ownership record.')
    return record


def list_sessions():
    if sys.platform != 'win32':
        return {'sessions': [], 'supported': False}
    rows = []
    for path in sorted(registry_dir().glob('*.json')):
        try:
            record = read_record(path)
            owner, driver = process_state(record['owner']), process_state(record['driver'])
            state = ('unknown' if 'unknown' in (owner, driver) else
                     'finished' if driver == 'gone' else
                     'orphaned_driver' if owner == 'gone' else 'active')
            rows.append({**record, 'state': state, 'owner_state': owner, 'driver_state': driver})
        except (OSError, ValueError, KeyError, TypeError):
            rows.append({'record': path.name, 'state': 'invalid'})
    return {'supported': True, 'sessions': rows,
            'note': 'Tracks drivers launched by this version only. No URLs, cookies or browser process enumeration. Unknown owners are never cleaned.'}


def cleanup_session(session_id, dry_run=True):
    with desktop_lease():
        path = record_path(session_id)
        record = read_record(path)
        if process_state(record['owner']) != 'gone':
            raise RuntimeError('Owner is alive or unknown; cleanup refused.')
        driver = record['driver']
        # Check identity and terminate using the SAME handle: PID reuse cannot
        # redirect termination to a newly started process after verification.
        with process_handle(driver['pid'], terminate=not dry_run) as (api, handle):
            state = api.WaitForSingleObject(handle, 0) if handle is not None else 0
            if state not in (0, 258):
                raise ctypes.WinError(ctypes.get_last_error())
            present = (handle is not None and state == 258
                       and identity_from_handle(api, handle, driver['pid']) == driver)
            if dry_run:
                return {'session_id': session_id, 'dry_run': True,
                        'action': 'terminate_owned_driver' if present else 'remove_finished_record'}
            if present:
                if not api.TerminateProcess(handle, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
                if api.WaitForSingleObject(handle, 5000) != 0:
                    raise RuntimeError('Driver termination not confirmed; ownership record retained.')
        path.unlink()
        return {'session_id': session_id, 'cleaned': True, 'driver_terminated': present,
                'note': 'Edge windows are not killed; close any remaining window manually.'}


class OwnedService(Service):
    session_id = None

    def start(self):
        try:
            super().start()
            self.session_id = register_driver(self.process.pid)
        except Exception:
            self.stop()
            raise

    def stop(self):
        try:
            super().stop()
        finally:
            session_id = self.session_id
            if session_id:
                path = record_path(session_id)
                try:
                    if process_state(read_record(path)['driver']) == 'gone':
                        path.unlink()
                        self.session_id = None
                except (OSError, ValueError, KeyError, TypeError):
                    pass  # Retain uncertain records for diagnosis.
