from __future__ import annotations

import sys
from pathlib import Path


class PortableAppPaths:
    """Keep configuration and models beside the desktop executable."""

    def __init__(self, source_root: Path | None = None) -> None:
        self._source_root = source_root or Path(__file__).resolve().parent.parent.parent

    def application_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return self._source_root

    def config_file(self) -> Path:
        return self.application_dir() / "config.json"

    def bundled_resource(self, name: str) -> Path:
        bundle_root = Path(getattr(sys, "_MEIPASS", self.application_dir()))
        return bundle_root / "resources" / name

    def resolve_data_path(self, path: str | Path) -> Path:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.application_dir() / resolved
        return resolved


DEFAULT_APP_PATHS = PortableAppPaths()
