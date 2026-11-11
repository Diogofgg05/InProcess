"""Best-effort process grouping, not a universal definition of application."""
import platform
from pathlib import Path
import psutil


def windows_groups() -> tuple[set[int],set[int]]:
    import ctypes
    from ctypes import wintypes
    applications,services = set(),set()
    user32 = ctypes.WinDLL('user32',use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type,wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    def visit(hwnd,_):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd)>0:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            applications.add(pid.value)
        return True
    if not user32.EnumWindows(callback_type(visit),0):
        raise OSError('EnumWindows indisponível.')
    for service in psutil.win_service_iter():
        try:
            pid = service.pid()
            if pid: services.add(pid)
        except psutil.Error:
            continue
    return applications,services


def linux_group(pid: int) -> str:
    try:
        cgroup = Path(f'/proc/{pid}/cgroup').read_text(encoding='utf-8')
        if '.service' in cgroup: return 'service'
        if 'app-' in cgroup and '.scope' in cgroup: return 'application'
        return 'process'
    except (OSError,UnicodeError):
        return 'unknown'
