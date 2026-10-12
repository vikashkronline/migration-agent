"""Platform process supervision for explicitly trusted native code."""

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast


class SupervisedProcess(Protocol):
    stdout: BinaryIO
    pid: int

    def poll(self) -> int | None: ...
    def close(self) -> None: ...


class WindowsJobProcess:
    """Atomic job assignment prevents an unsupervised child creation window."""

    kernel: Any
    job: Any
    handle: Any
    stdout: BinaryIO
    pid: int
    _closed: bool

    def __init__(self, argv: list[str], cwd: Path, env: dict[str, str]) -> None:
        if sys.platform != "win32":
            raise ValueError("EXECUTION_POLICY_UNSUPPORTED: Windows Job Objects unavailable.")
        import msvcrt
        from ctypes import wintypes as w

        kernel: Any = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel = kernel
        for name, args, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            ("SetInformationJobObject", [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
            (
                "QueryInformationJobObject",
                [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p],
                w.BOOL,
            ),
            (
                "InitializeProcThreadAttributeList",
                [ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.c_void_p],
                w.BOOL,
            ),
            (
                "UpdateProcThreadAttribute",
                [
                    ctypes.c_void_p,
                    w.DWORD,
                    ctypes.c_size_t,
                    ctypes.c_void_p,
                    ctypes.c_size_t,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ],
                w.BOOL,
            ),
            ("DeleteProcThreadAttributeList", [ctypes.c_void_p], None),
            (
                "CreateProcessW",
                [
                    w.LPCWSTR,
                    w.LPWSTR,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    w.BOOL,
                    w.DWORD,
                    ctypes.c_void_p,
                    w.LPCWSTR,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ],
                w.BOOL,
            ),
            ("WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD),
            ("GetExitCodeProcess", [w.HANDLE, ctypes.c_void_p], w.BOOL),
            ("TerminateJobObject", [w.HANDLE, w.UINT], w.BOOL),
            ("CloseHandle", [w.HANDLE], w.BOOL),
        ):
            function = getattr(kernel, name)
            function.argtypes, function.restype = args, result

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", w.DWORD),
                ("min_ws", ctypes.c_size_t),
                ("max_ws", ctypes.c_size_t),
                ("active", w.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", w.DWORD),
                ("scheduling", w.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        class Startup(ctypes.Structure):
            _fields_ = [
                ("cb", w.DWORD),
                ("reserved", w.LPWSTR),
                ("desktop", w.LPWSTR),
                ("title", w.LPWSTR),
                ("x", w.DWORD),
                ("y", w.DWORD),
                ("xsize", w.DWORD),
                ("ysize", w.DWORD),
                ("xchars", w.DWORD),
                ("ychars", w.DWORD),
                ("fill", w.DWORD),
                ("flags", w.DWORD),
                ("show", w.WORD),
                ("reserved_size", w.WORD),
                ("reserved_bytes", ctypes.c_void_p),
                ("stdin", w.HANDLE),
                ("stdout", w.HANDLE),
                ("stderr", w.HANDLE),
            ]

        class StartupEx(ctypes.Structure):
            _fields_ = [("startup", Startup), ("attributes", ctypes.c_void_p)]

        class ProcessInfo(ctypes.Structure):
            _fields_ = [
                ("process", w.HANDLE),
                ("thread", w.HANDLE),
                ("pid", w.DWORD),
                ("tid", w.DWORD),
            ]

        self.job = kernel.CreateJobObjectW(None, None)
        self.handle: Any = None
        self._closed = False
        read_fd, write_fd = os.pipe()
        self.stdout: BinaryIO = os.fdopen(read_fd, "rb", buffering=0)
        attributes: Any = None
        initialized = False
        try:
            if not self.job:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000 | 0x8 | 0x200 | 0x4
            limits.basic.active = 128
            limits.basic.job_time = 60 * 10_000_000
            limits.job_memory = 512 * 1024 * 1024
            if not kernel.SetInformationJobObject(
                self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            size = ctypes.c_size_t()
            kernel.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
            attributes = ctypes.create_string_buffer(size.value)
            if not kernel.InitializeProcThreadAttributeList(attributes, 2, 0, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            initialized = True
            jobs = (w.HANDLE * 1)(self.job)
            if not kernel.UpdateProcThreadAttribute(
                attributes, 0, 0x2000D, jobs, ctypes.sizeof(jobs), None, None
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            os.set_inheritable(write_fd, True)
            with open(os.devnull, "rb") as null:
                os.set_handle_inheritable(msvcrt.get_osfhandle(null.fileno()), True)
                handles = (w.HANDLE * 2)(
                    msvcrt.get_osfhandle(write_fd), msvcrt.get_osfhandle(null.fileno())
                )
                if not kernel.UpdateProcThreadAttribute(
                    attributes, 0, 0x20002, handles, ctypes.sizeof(handles), None, None
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                startup = StartupEx()
                startup.startup.cb = ctypes.sizeof(startup)
                startup.startup.flags = 0x100
                startup.startup.stdin = handles[1]
                startup.startup.stdout = startup.startup.stderr = handles[0]
                startup.attributes = ctypes.cast(attributes, ctypes.c_void_p)
                info = ProcessInfo()
                command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
                environment = ctypes.create_unicode_buffer(
                    "\0".join(
                        f"{key}={value}"
                        for key, value in sorted(env.items(), key=lambda item: item[0].upper())
                    )
                    + "\0\0"
                )
                if not kernel.CreateProcessW(
                    argv[0],
                    command_line,
                    None,
                    None,
                    True,
                    0x08000000 | 0x00080000 | 0x400,
                    environment,
                    str(cwd),
                    ctypes.byref(startup),
                    ctypes.byref(info),
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handle, self.pid = info.process, int(info.pid)
                kernel.CloseHandle(info.thread)
        except BaseException:
            if self.handle:
                kernel.TerminateJobObject(self.job, 1)
                kernel.CloseHandle(self.handle)
            if self.job:
                kernel.CloseHandle(self.job)
            self.stdout.close()
            raise
        finally:
            os.close(write_fd)
            if initialized:
                kernel.DeleteProcThreadAttributeList(attributes)

    def poll(self) -> int | None:
        if self.kernel.WaitForSingleObject(self.handle, 0) == 258:
            return None
        code = ctypes.c_uint32()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ValueError("NATIVE_PROCESS_UNVERIFIED: cannot observe process exit.")
        return int(code.value)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if not self.kernel.TerminateJobObject(self.job, 1):
                raise ValueError("NATIVE_CLEANUP_UNVERIFIED: cannot terminate validation job.")
            accounting = (ctypes.c_uint32 * 12)()
            deadline = time.monotonic() + 5
            while True:
                if not self.kernel.QueryInformationJobObject(
                    self.job, 1, accounting, ctypes.sizeof(accounting), None
                ):
                    raise ValueError("NATIVE_CLEANUP_UNVERIFIED: cannot query validation job.")
                # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION has four LARGE_INTEGER fields,
                # then four DWORD fields. ActiveProcesses is DWORD index 10.
                if accounting[10] == 0:
                    break
                if time.monotonic() >= deadline:
                    raise ValueError("NATIVE_CLEANUP_UNVERIFIED: job descendants remain active.")
                time.sleep(0.02)
        finally:
            self.kernel.CloseHandle(self.handle)
            self.kernel.CloseHandle(self.job)


class LinuxGroupProcess:
    """A separate guardian observes pipe EOF if the calling server crashes."""

    def __init__(self, argv: list[str], cwd: Path, env: dict[str, str]) -> None:
        if sys.platform != "linux":
            raise ValueError("EXECUTION_POLICY_UNSUPPORTED: native supervision unavailable.")
        self.process: subprocess.Popen[bytes] = subprocess.Popen(
            [sys.executable, "-I", str(Path(__file__).with_name("native_guardian.py")), *argv],
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            start_new_session=True,
        )
        assert self.process.stdout is not None
        self.stdout: BinaryIO = cast(BinaryIO, self.process.stdout)
        self.pid = self.process.pid

    def poll(self) -> int | None:
        return self.process.poll()

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired as error:
            raise ValueError("NATIVE_CLEANUP_UNVERIFIED: guardian did not finish.") from error
        if code == 125:
            raise ValueError("NATIVE_CLEANUP_UNVERIFIED: guardian cleanup failed.")


def launch_native(argv: list[str], cwd: Path, env: dict[str, str]) -> SupervisedProcess:
    if os.name == "nt":
        return WindowsJobProcess(argv, cwd, env)
    return LinuxGroupProcess(argv, cwd, env)
