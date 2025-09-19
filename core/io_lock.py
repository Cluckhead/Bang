# Purpose: Centralize safe, cross-process file I/O with file-based locks.
# Provides locking wrappers and installs a global monkey-patch so all
# pandas CSV reads/writes use file locks, minimizing race-condition risk.

from __future__ import annotations

import os
import io
import csv
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional, Any

import pandas as pd
from filelock import FileLock, Timeout
import logging


_logger = logging.getLogger(__name__)


# Defaults can be tuned via env vars
READ_TIMEOUT_DEFAULT: float = float(os.getenv("SDC_FILELOCK_READ_TIMEOUT", "15"))
WRITE_TIMEOUT_DEFAULT: float = float(os.getenv("SDC_FILELOCK_WRITE_TIMEOUT", "30"))


def _as_path(path_or_buf: Any) -> Optional[Path]:
    """Return Path if argument is a filesystem path; else None.

    Handles str, os.PathLike. File-like objects or buffers return None.
    """
    if isinstance(path_or_buf, (str, os.PathLike)):
        try:
            return Path(path_or_buf)
        except Exception:
            return None
    return None


def _lockfile_for(path: Path) -> Path:
    """Return a lock file path next to the target (e.g., file.csv.lock)."""
    # Always suffix with .lock (keep original suffix too to avoid collisions)
    return path.with_suffix(path.suffix + ".lock")


def read_csv_locked(path: str | os.PathLike, *, timeout: float = READ_TIMEOUT_DEFAULT, **kwargs) -> pd.DataFrame:
    """Read a CSV under a file lock to avoid reading while another process writes.

    Falls back to normal read when the argument is not a filesystem path.
    Additional pandas.read_csv kwargs are supported.
    """
    target = _as_path(path)
    if target is None:
        return pd.read_csv(path, **kwargs)

    lock = FileLock(str(_lockfile_for(target)), timeout=timeout)
    try:
        with lock:
            return pd.read_csv(str(target), **kwargs)
    except Timeout as e:
        _logger.error(f"Timeout acquiring read lock for {target}: {e}")
        raise


def to_csv_locked(
    df: pd.DataFrame,
    path_or_buf: Any = None,
    *args,
    timeout: float = WRITE_TIMEOUT_DEFAULT,
    **kwargs,
) -> None:
    """Write CSV with a lock. Uses atomic replace for overwrite writes.

    - If path_or_buf is a filesystem path and mode is overwrite ('w' or default):
      write to a temporary file in the same directory then os.replace().
    - If mode is append ('a'/'a+'), write directly under the lock.
    - If path_or_buf is a buffer/file-like, falls back to normal behavior (no lock).
    """
    target = _as_path(path_or_buf)
    if target is None:
        # Non-path buffer → no lock possible
        return pd.DataFrame.to_csv(df, path_or_buf, *args, **kwargs)

    # Ensure parent exists
    target.parent.mkdir(parents=True, exist_ok=True)

    mode = kwargs.get("mode", "w") or "w"
    lock = FileLock(str(_lockfile_for(target)), timeout=timeout)

    try:
        with lock:
            if "a" in mode:
                # Append is not atomic, but lock ensures exclusive write
                return pd.DataFrame.to_csv(df, str(target), *args, **kwargs)
            # Overwrite: write atomically via a temporary file
            # Remove "mode" if caller passed it; we'll let pandas open default 'w'
            if "mode" in kwargs:
                kwargs = {k: v for k, v in kwargs.items() if k != "mode"}
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent), prefix=target.name + ".tmp-", suffix=target.suffix or ".csv"
            )
            os.close(tmp_fd)
            try:
                pd.DataFrame.to_csv(df, tmp_path, *args, **kwargs)
                os.replace(tmp_path, str(target))  # atomic on same volume
            finally:
                # If anything failed before replace, clean up tmp file
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
    except Timeout as e:
        _logger.error(f"Timeout acquiring write lock for {target}: {e}")
        raise


def append_rows_locked(
    path: str | os.PathLike,
    rows: Iterable[Iterable[Any]],
    header: Optional[Iterable[str]] = None,
    *,
    timeout: float = WRITE_TIMEOUT_DEFAULT,
    newline: str = "",
    encoding: str = "utf-8",
) -> None:
    """Append rows to a CSV file under a lock. Optionally write a header first.

    This is a convenience for places using csv.writer directly.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(_lockfile_for(target)), timeout=timeout)

    try:
        with lock:
            file_exists = target.exists()
            with target.open("a", newline=newline, encoding=encoding) as f:
                writer = csv.writer(f)
                if header is not None and not file_exists:
                    writer.writerow(list(header))
                for row in rows:
                    writer.writerow(list(row))
    except Timeout as e:
        _logger.error(f"Timeout acquiring append lock for {target}: {e}")
        raise


_installed_flag = False


def install_pandas_file_locks() -> None:
    """Globally patch pandas read_csv and DataFrame.to_csv to use file locks.

    Idempotent: safe to call multiple times. Can be disabled by env var:
    SDC_FILELOCK_DISABLE=1
    """
    global _installed_flag
    if _installed_flag:
        return
    if os.getenv("SDC_FILELOCK_DISABLE", "0") == "1":
        _logger.info("SDC file locks disabled via SDC_FILELOCK_DISABLE=1")
        _installed_flag = True
        return

    # Wrap pd.read_csv
    _orig_read_csv = pd.read_csv

    def _read_csv_wrapper(filepath_or_buffer: Any, *args, **kwargs):
        target = _as_path(filepath_or_buffer)
        if target is None:
            return _orig_read_csv(filepath_or_buffer, *args, **kwargs)
        timeout = kwargs.pop("lock_timeout", READ_TIMEOUT_DEFAULT)
        lock = FileLock(str(_lockfile_for(target)), timeout=timeout)
        with lock:
            return _orig_read_csv(str(target), *args, **kwargs)

    pd.read_csv = _read_csv_wrapper  # type: ignore[assignment]

    # Wrap DataFrame.to_csv
    _orig_to_csv = pd.DataFrame.to_csv

    def _to_csv_wrapper(self: pd.DataFrame, path_or_buf: Any = None, *args, **kwargs):
        target = _as_path(path_or_buf)
        if target is None:
            return _orig_to_csv(self, path_or_buf, *args, **kwargs)
        timeout = kwargs.pop("lock_timeout", WRITE_TIMEOUT_DEFAULT)
        mode = kwargs.get("mode", "w") or "w"
        lock = FileLock(str(_lockfile_for(target)), timeout=timeout)
        target.parent.mkdir(parents=True, exist_ok=True)
        with lock:
            if "a" in mode:
                return _orig_to_csv(self, str(target), *args, **kwargs)
            # overwrite atomically
            if "mode" in kwargs:
                kwargs = {k: v for k, v in kwargs.items() if k != "mode"}
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent), prefix=target.name + ".tmp-", suffix=target.suffix or ".csv"
            )
            os.close(tmp_fd)
            try:
                _orig_to_csv(self, tmp_path, *args, **kwargs)
                os.replace(tmp_path, str(target))
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

    pd.DataFrame.to_csv = _to_csv_wrapper  # type: ignore[assignment]

    _installed_flag = True
    _logger.debug("Installed global file-locked CSV I/O wrappers for pandas")


__all__ = [
    "install_pandas_file_locks",
    "read_csv_locked",
    "to_csv_locked",
    "append_rows_locked",
]


