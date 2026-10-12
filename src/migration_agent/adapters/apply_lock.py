"""Portable nonblocking OS lock held throughout the apply critical section."""

import importlib
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


class ExclusiveApplyLock:
    def __init__(self, lock_root: Path) -> None:
        self.root = lock_root.resolve()
        self.handle: BinaryIO | None = None

    @contextmanager
    def acquire(self, project_id: str) -> Iterator[None]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project_id):
            raise ValueError("INVALID_ID: unsafe lock project identity.")
        if self.handle is not None:
            raise ValueError("WRITER_BUSY: lock already held.")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{project_id}.apply.lock"
        if path.is_symlink() or path.is_junction():
            raise ValueError("UNSAFE_LOCK_PATH: lock cannot follow links.")
        handle = path.open("a+b")
        acquired = False
        try:
            if handle.seek(0, 2) == 0:
                handle.write(b"\x00")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    msvcrt = importlib.import_module("msvcrt")

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl = importlib.import_module("fcntl")
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError("WRITER_BUSY: exclusive apply lock unavailable.") from None
            acquired = True
            self.handle = handle
            yield
        finally:
            self.handle = None
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt = importlib.import_module("msvcrt")

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl = importlib.import_module("fcntl")
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def verify(self) -> None:
        if self.handle is None or self.handle.closed:
            raise ValueError("LOCK_LOST: apply writer no longer owns its OS lock.")
