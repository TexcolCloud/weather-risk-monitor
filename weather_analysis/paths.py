"""Writable runtime paths shared by application components."""

import os
from collections.abc import Mapping
from pathlib import Path


APP_NAME = "weather-analysis"


def resolve_data_dir(
    environ: Mapping[str, str] | None = None,
    os_name: str | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve a user-writable application data directory."""
    environ = os.environ if environ is None else environ
    override = environ.get("WEATHER_ANALYSIS_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    os_name = os.name if os_name is None else os_name
    home = Path.home() if home is None else home
    if os_name == "nt":
        base = Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    else:
        base = Path(environ.get("XDG_STATE_HOME") or home / ".local" / "state")
    return (base / APP_NAME).expanduser().resolve()


APP_DATA_DIR = resolve_data_dir()
