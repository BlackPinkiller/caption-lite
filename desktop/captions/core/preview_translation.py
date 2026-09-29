"""Input identity for bounded, per-cue preview reuse. No provider or UI calls."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from captions.core.translation_alignment import source_extends_preview


@dataclass(frozen=True)
class PreviewInput:
    cue_id: int
    source: str
    context: tuple[str, ...]
    settings_digest: str

    @classmethod
    def create(
        cls, cue_id: int, source: str, context: tuple[str, ...],
        settings: Mapping[str, Any],
    ) -> PreviewInput:
        # Conservative identity: any settings change prevents reuse. Keep keys
        # out of the identity itself and never write the digest to diagnostics.
        serialized = json.dumps(settings, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return cls(cue_id, source, context, digest)

    def can_extend_to(self, current: PreviewInput) -> bool:
        return (
            self.cue_id == current.cue_id
            and self.context == current.context
            and self.settings_digest == current.settings_digest
            and source_extends_preview(self.source, current.source)
        )


@dataclass(frozen=True)
class CompletedPreview:
    request: PreviewInput
    translation: str
