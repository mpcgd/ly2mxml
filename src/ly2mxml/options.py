"""Represent export-policy switches shared by the CLI and Python API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ly2mxml.model.score import PartCombineMode


CueMode = Literal["ignore", "include"]


@dataclass(frozen=True, slots=True)
class ExportOptions:
    """Hold the bounded export-policy choices supported by the converter."""

    partcombine_mode: PartCombineMode = "separate"
    cue_mode: CueMode = "ignore"

    @property
    def include_cues(self) -> bool:
        """Return ``True`` when cue-note material should be emitted."""

        return self.cue_mode == "include"