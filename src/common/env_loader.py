from __future__ import annotations

import os
from pathlib import Path


_ENV_LOADED = False


def load_project_env(
    env_path: str | Path | None = None,
    *,
    override: bool = False,
) -> Path | None:
    """Load project-level environment variables from .env if the file exists."""
    global _ENV_LOADED

    path = Path(env_path) if env_path is not None else _project_root() / ".env"
    path = path.expanduser().resolve()
    if not path.exists():
        return None

    if _ENV_LOADED and not override:
        return path

    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_env_file_without_dependency(path, override=override)
    else:
        load_dotenv(dotenv_path=path, override=override, encoding="utf-8")

    _ENV_LOADED = True
    return path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_env_file_without_dependency(path: Path, *, override: bool) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        if line.startswith("export "):
            line = line.removeprefix("export ").strip()

        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = _strip_inline_comment(value.strip())
        if not key or (key in os.environ and not override):
            continue

        os.environ[key] = _strip_matching_quotes(value)


def _strip_inline_comment(value: str) -> str:
    quote_char = ""
    for index, char in enumerate(value):
        if char in {"'", '"'}:
            if quote_char == char:
                quote_char = ""
            elif not quote_char:
                quote_char = char
        elif char == "#" and not quote_char:
            return value[:index].rstrip()
    return value


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
