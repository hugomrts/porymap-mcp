"""Atomic file-write helper.

All on-disk writes performed by ``porymap-mcp`` go through :func:`write_atomic`
so a crash mid-write cannot leave a half-written map file. The implementation
is the classic write-to-temp + ``os.replace`` dance.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically.

    A temporary file is created in the destination directory, then renamed
    onto the target path via :func:`os.replace`, which is atomic on POSIX
    and on modern Windows. On failure, the temporary file is removed.

    The caller is responsible for ensuring ``path.parent`` exists.
    """
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=directory,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def write_atomic_text(path: Path, text: str, *, newline: str = "\n") -> None:
    """Write a UTF-8 text file atomically with the given line-ending."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline != "\n":
        normalized = normalized.replace("\n", newline)
    write_atomic(path, normalized.encode("utf-8"))
