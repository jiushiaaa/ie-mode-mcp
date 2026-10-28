"""Read-only session diagnostics; never unlock or change desktop settings."""
import ctypes
from ctypes import wintypes
import platform


class _SessionLevel1(ctypes.Structure):
    # WTSINFOEX_LEVEL1_W. Names and timestamps are never exposed to callers.
    _fields_ = [
        ("session_id", wintypes.DWORD), ("connection_state", ctypes.c_int),
        ("flags", wintypes.LONG), ("station", wintypes.WCHAR * 33),
        ("user", wintypes.WCHAR * 21), ("domain", wintypes.WCHAR * 18),
        ("times", ctypes.c_longlong * 5), ("counters", wintypes.DWORD * 6),
    ]


class _SessionInfo(ctypes.Structure):
    _fields_ = [("level", wintypes.DWORD), ("data", _SessionLevel1)]


def desktop_status():
    """Return locked/unlocked/unknown for this process's Windows session."""
    if platform.system() != "Windows":
        return {"state": "unknown", "reason": "Windows session diagnostics unavailable"}
    api = ctypes.WinDLL("wtsapi32", use_last_error=True)
    query = api.WTSQuerySessionInformationW
    query.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
                      ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL
    api.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    api.WTSFreeMemory.restype = None
    buffer, size = ctypes.c_void_p(), wintypes.DWORD()
    # WTS_CURRENT_SERVER, WTS_CURRENT_SESSION, WTSSessionInfoEx.
    if not query(None, 0xFFFFFFFF, 25, ctypes.byref(buffer), ctypes.byref(size)):
        return {"state": "unknown", "winerror": ctypes.get_last_error()}
    try:
        if size.value < ctypes.sizeof(_SessionInfo):
            return {"state": "unknown", "reason": "Incomplete WTS session information"}
        info = ctypes.cast(buffer, ctypes.POINTER(_SessionInfo)).contents
        if info.level != 1:
            return {"state": "unknown", "reason": "Unsupported WTS information level"}
        return {"state": {0: "locked", 1: "unlocked"}.get(info.data.flags, "unknown"),
                "session_id": info.data.session_id,
                "connection_state": info.data.connection_state}
    finally:
        api.WTSFreeMemory(buffer)
