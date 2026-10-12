"""Linux-only guardian entry point; launched with isolated Python and fixed argv."""

import contextlib
import ctypes
import importlib
import os
import select
import subprocess
import sys
import time


def main() -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    libc.prctl.restype = ctypes.c_int
    # Reap orphaned descendants instead of treating persistent zombies as live jobs.
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        return 125
    process = subprocess.Popen(
        sys.argv[1:], shell=False, start_new_session=True, stdin=subprocess.DEVNULL
    )
    code: int | None = 1
    cleanup_failed = False
    posix_os = importlib.import_module("os")
    posix_signal = importlib.import_module("signal")
    try:
        while process.poll() is None:
            readable, _, _ = select.select([sys.stdin.buffer], [], [], 0.1)
            if readable and not os.read(0, 1):
                break
        code = process.poll() if process.poll() is not None else 1
    finally:
        with contextlib.suppress(ProcessLookupError):
            posix_os.killpg(process.pid, posix_signal.SIGKILL)
        process.wait(timeout=5)
        deadline = time.monotonic() + 5
        while True:
            with contextlib.suppress(ChildProcessError):
                while posix_os.waitpid(-1, posix_os.WNOHANG)[0] > 0:
                    pass
            try:
                posix_os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            if time.monotonic() > deadline:
                cleanup_failed = True
                break
            time.sleep(0.02)
    return 125 if cleanup_failed else int(code or 0)


if __name__ == "__main__":
    raise SystemExit(main())
