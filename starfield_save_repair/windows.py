"""Windows save-folder discovery and read-only game-process detection."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


def default_save_directory():
    candidates = []
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                documents = winreg.QueryValueEx(key, "Personal")[0]
                candidates.append(Path(os.path.expandvars(documents)))
        except OSError:
            pass
    for variable in ("OneDrive", "OneDriveConsumer"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "Documents")
    candidates.extend((Path.home() / "Documents", Path.home() / "OneDrive" / "Documents"))
    folders = [p / "My Games" / "Starfield" / "Saves" for p in candidates]
    return next((p for p in folders if p.is_dir()), folders[0])


def repair_directory():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return base / "StarfieldSaveRepair" / "repairs"


def starfield_running():
    if os.name != "nt":
        return False

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        function.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("Could not check whether Starfield is running. Close the game and try again.")
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.szExeFile.casefold() == "starfield.exe":
                return True
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise OSError("Could not finish checking game processes. Try again before repairing.")
        return False
    finally:
        kernel.CloseHandle(snapshot)
