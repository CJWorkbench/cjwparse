import contextlib
import os
import tempfile
from pathlib import Path
from typing import ContextManager


@contextlib.contextmanager
def tempfile_context(prefix=None, suffix=None, dir=None) -> ContextManager[Path]:
    fd, filename = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=dir)
    os.close(fd)
    path = Path(filename)
    try:
        yield path
    finally:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
