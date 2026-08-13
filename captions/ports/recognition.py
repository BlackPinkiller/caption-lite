from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


ASR_SAMPLE_RATE = 16000
VAD_WINDOW_SIZE = 512


@dataclass(frozen=True)
class RecognitionUpdate:
    text: str
    endpoint: bool


class StreamingRecognition(Protocol):
    def reset(self) -> None:
        ...

    def accept(self, samples: np.ndarray) -> RecognitionUpdate:
        ...


class RecognitionBackend(Protocol):
    """Create streaming ASR and VAD instances for the selected model."""

    def create_streaming(self, config) -> StreamingRecognition:
        ...

    def create_vad(self, config):
        ...
