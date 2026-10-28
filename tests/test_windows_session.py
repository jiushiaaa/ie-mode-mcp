import ctypes
from unittest.mock import Mock

import pytest

from ie_mode_mcp import windows_session as session


@pytest.mark.parametrize('flag,state', [(0, 'locked'), (1, 'unlocked'), (-1, 'unknown')])
def test_wts_state_is_read_without_exposing_names_and_buffer_is_freed(monkeypatch, flag, state):
    monkeypatch.setattr(session.platform, 'system', lambda: 'Windows')
    info = session._SessionInfo()
    info.level, info.data.session_id, info.data.flags = 1, 3, flag
    info.data.user = 'private-user'
    api = Mock()

    def query(server, session_id, info_class, buffer, size):
        assert (server, session_id, info_class) == (None, 0xFFFFFFFF, 25)
        buffer._obj.value = ctypes.addressof(info)
        size._obj.value = ctypes.sizeof(info)
        return True

    api.WTSQuerySessionInformationW.side_effect = query
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw: api, raising=False)
    assert session.desktop_status() == {'state': state, 'session_id': 3, 'connection_state': 0}
    api.WTSFreeMemory.assert_called_once()


def test_failed_session_query_is_unknown(monkeypatch):
    monkeypatch.setattr(session.platform, 'system', lambda: 'Windows')
    api = Mock()
    api.WTSQuerySessionInformationW.return_value = False
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw: api, raising=False)
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 5, raising=False)
    assert session.desktop_status() == {'state': 'unknown', 'winerror': 5}
    api.WTSFreeMemory.assert_not_called()
