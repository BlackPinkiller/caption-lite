from __future__ import annotations

from dataclasses import dataclass

from captions.core.translation_alignment import source_extends_preview


@dataclass
class CaptionEntry:
    text: str
    kind: str
    opacity: float = 1.0
    current: bool = False


@dataclass
class CaptionCue:
    cue_id: int
    source: str
    translation: str


class CaptionState:
    """Caption history and display selection without UI dependencies."""

    def __init__(self) -> None:
        self.source = ""
        self.translation = ""
        self.translation_source = ""
        self.cue_id = 0
        self._cleared_through_cue_id = 0
        self.previous_cues: list[CaptionCue] = []

    def set_content(
        self,
        source: str | None = None,
        translation: str | None = None,
    ) -> None:
        if source is not None:
            if not source_extends_preview(self.translation_source or self.source, source):
                self.translation = ""
                self.translation_source = ""
            self.source = source
        if translation is not None:
            self.translation = translation
            self.translation_source = self.source if translation else ""

    def set_cue(
        self, cue_id: int, source: str, translation: str,
        *, translation_source: str | None = None,
    ) -> None:
        if cue_id <= self._cleared_through_cue_id:
            return
        source = source.strip()
        translation = translation.strip()
        if cue_id != self.cue_id:
            if self.cue_id and (self.source or self.translation):
                self.previous_cues.append(
                    CaptionCue(self.cue_id, self.source, self.translation)
                )
                self.previous_cues = self.previous_cues[-6:]
            self.cue_id = cue_id
        self.source = source
        self.translation = translation
        self.translation_source = (
            source if translation_source is None else translation_source
        ) if translation else ""

    def set_translation(self, cue_id: int, translation: str) -> bool:
        translation = translation.strip()
        if cue_id == self.cue_id:
            self.translation = translation
            self.translation_source = self.source if translation else ""
            return True
        for cue in reversed(self.previous_cues):
            if cue.cue_id == cue_id:
                cue.translation = translation
                return True
        return False

    def clear(self) -> None:
        # Hiding captions must not make a delayed result from an older cue new.
        self._cleared_through_cue_id = max(self._cleared_through_cue_id, self.cue_id)
        self.source = self.translation = ""
        self.translation_source = ""
        self.cue_id = 0
        self.previous_cues.clear()

    def visible_entries(
        self,
        mode: str,
        max_sentences: int,
        old_opacity: float,
        preview_opacity: float,
    ) -> list[CaptionEntry]:
        minimum = 2 if mode == "bilingual" else 1
        limit = max(minimum, min(6, max_sentences))
        current = CaptionCue(self.cue_id, self.source, self.translation)

        if mode == "source":
            rows = [
                CaptionEntry(cue.source, "source", old_opacity)
                for cue in self.previous_cues
                if cue.source
            ]
            if current.source:
                rows.append(CaptionEntry(current.source, "source", preview_opacity, True))
            return rows[-limit:]

        if mode == "translation":
            rows = [
                CaptionEntry(cue.translation, "translation", old_opacity)
                for cue in self.previous_cues
                if cue.translation
            ]
            if current.translation:
                rows.append(
                    CaptionEntry(current.translation, "translation", preview_opacity, True)
                )
            return rows[-limit:]

        current_rows: list[CaptionEntry] = []
        if current.source:
            current_rows.append(CaptionEntry(current.source, "source", preview_opacity, True))
        if current.translation:
            current_rows.append(
                CaptionEntry(current.translation, "translation", preview_opacity, True)
            )
        remaining = max(0, limit - len(current_rows))
        older_groups: list[list[CaptionEntry]] = []
        for cue in reversed(self.previous_cues):
            if remaining <= 0:
                break
            pair = [
                CaptionEntry(cue.source, "source", old_opacity),
                CaptionEntry(cue.translation, "translation", old_opacity),
            ]
            pair = [row for row in pair if row.text]
            if not pair:
                continue
            if remaining == 1:
                older_groups.append(
                    [
                        next(
                            (row for row in pair if row.kind == "translation"),
                            pair[-1],
                        )
                    ]
                )
                remaining = 0
            else:
                selected = pair[-remaining:]
                older_groups.append(selected)
                remaining -= len(selected)
        return [
            row for group in reversed(older_groups) for row in group
        ] + current_rows
