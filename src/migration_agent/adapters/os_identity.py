"""Stable local identities using the standard library on Windows and POSIX."""

import csv
import ctypes
import os
import subprocess
from ctypes import wintypes
from pathlib import Path

from migration_agent.domain.security import SecurityConfigurationError


def _windows_sid() -> str:
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.OpenThreadToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.BOOL,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenThreadToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetCurrentThread.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    thread_token = wintypes.HANDLE()
    if advapi.OpenThreadToken(kernel.GetCurrentThread(), 8, True, ctypes.byref(thread_token)):
        kernel.CloseHandle(thread_token)
        raise SecurityConfigurationError(
            "IDENTITY_UNSUPPORTED: impersonated threads cannot administer access."
        )
    if ctypes.get_last_error() != 1008:
        raise SecurityConfigurationError("IDENTITY_FAILED: cannot inspect thread identity.")
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise SecurityConfigurationError("IDENTITY_FAILED: cannot open the process token.")
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not 0 < size.value <= 65536:
            raise SecurityConfigurationError("IDENTITY_FAILED: invalid token information size.")
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise SecurityConfigurationError("IDENTITY_FAILED: cannot read TokenUser.")
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise SecurityConfigurationError("IDENTITY_FAILED: cannot convert TokenUser SID.")
        try:
            return str(text.value)
        finally:
            kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
    finally:
        kernel.CloseHandle(token)


def _fallback_sid() -> str:
    executable = windows_system_directory() / "whoami.exe"
    result = subprocess.run(
        [str(executable), "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        shell=False,
        timeout=5,
    )
    rows = list(csv.reader(result.stdout.splitlines()))
    if result.returncode or len(rows) != 1 or len(rows[0]) != 2:
        raise SecurityConfigurationError("IDENTITY_FAILED: cannot resolve the Windows SID.")
    return rows[0][1]


def windows_system_directory() -> Path:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    kernel.GetSystemDirectoryW.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    size = kernel.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < size < len(buffer):
        raise SecurityConfigurationError(
            "IDENTITY_FAILED: trusted system directory is unavailable."
        )
    return Path(buffer.value)


def windows_program_data_directory() -> Path:
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.SHGetFolderPathW.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
    ]
    shell.SHGetFolderPathW.restype = wintypes.LONG
    buffer = ctypes.create_unicode_buffer(32768)
    if shell.SHGetFolderPathW(None, 0x23, None, 0, buffer) != 0 or not buffer.value:
        raise SecurityConfigurationError(
            "IDENTITY_FAILED: trusted common application data directory is unavailable."
        )
    return Path(buffer.value)


def current_os_identity() -> str:
    if os.name != "nt":
        uid_function = vars(os)["geteuid"]
        machine_file = next(
            (
                path
                for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id"))
                if path.is_file()
            ),
            None,
        )
        if machine_file is None:
            raise SecurityConfigurationError(
                "IDENTITY_FAILED: stable OS machine identity is required."
            )
        machine = machine_file.read_text(encoding="ascii").strip()
        if len(machine) != 32 or any(char not in "0123456789abcdef" for char in machine):
            raise SecurityConfigurationError("IDENTITY_FAILED: malformed OS machine identity.")
        return f"posix:{machine}:uid:{uid_function()}"
    try:
        sid = _windows_sid()
    except (AttributeError, NotImplementedError):
        sid = _fallback_sid()
    if not sid.startswith("S-1-") or any(c not in "S-0123456789" for c in sid):
        raise SecurityConfigurationError("IDENTITY_FAILED: malformed Windows SID.")
    return f"windows:{sid}"
