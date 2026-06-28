from __future__ import annotations

import sys
from typing import TextIO


def configure_utf8_stdio() -> None:
    """Giữ tiếng Việt CLI đọc được trên terminal Windows cũ."""
    _configure_stream(sys.stdout)
    _configure_stream(sys.stderr)


def _configure_stream(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
