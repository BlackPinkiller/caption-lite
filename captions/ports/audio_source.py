from __future__ import annotations

from types import TracebackType
from typing import Protocol

import numpy as np


class AudioCapture(Protocol):
    @property
    def name(self) -> str:
        ...

    def __enter__(self) -> "AudioCapture":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...

    def read(self, num_frames: int) -> np.ndarray:
        ...


class AudioSource(Protocol):
    """Open the host's current system-playback audio stream."""

    def open_default_output(
        self,
        *,
        sample_rate: int,
        channels: int,
        block_size: int,
    ) -> AudioCapture:
        ...
