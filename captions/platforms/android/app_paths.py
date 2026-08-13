from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths


class AndroidAppPaths:
    def __init__(
        self,
        data_root: Path | None = None,
        resource_root: Path | None = None,
    ) -> None:
        self._data_root = data_root
        self._resource_root = resource_root or Path(__file__).resolve().parents[3]

    def application_dir(self) -> Path:
        if self._data_root is not None:
            return self._data_root
        location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if not location:
            raise RuntimeError("Android 应用数据目录不可用")
        return Path(location)

    def config_file(self) -> Path:
        return self.application_dir() / "config.json"

    def bundled_resource(self, name: str) -> Path:
        return self._resource_root / "resources" / name

    def resolve_data_path(self, path: str | Path) -> Path:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.application_dir() / resolved
        return resolved
