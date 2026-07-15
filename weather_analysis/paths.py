"""Writable runtime paths shared by application components."""

import os
from collections.abc import Mapping
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_data_dir(
    environ: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> Path:
    """Resolve the runtime data directory, defaulting to the project root."""
    environ = os.environ if environ is None else environ
    override = environ.get("WEATHER_ANALYSIS_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    return (project_root or PROJECT_ROOT).expanduser().resolve()


APP_DATA_DIR = resolve_data_dir()
