from __future__ import annotations

from typing import Protocol


class GlobalShortcut(Protocol):
    activated: object

    def install(self, application) -> bool:
        ...

    def uninstall(self) -> None:
        ...
