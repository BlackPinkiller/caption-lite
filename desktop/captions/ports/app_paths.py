from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AppPaths(Protocol):
    """Resolve writable application data and bundled resources."""

    def application_dir(self) -> Path:
        ...

    def config_file(self) -> Path:
        ...

    def bundled_resource(self, name: str) -> Path:
        ...

    def resolve_data_path(self, path: str | Path) -> Path:
        ...
