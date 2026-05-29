from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ly2mxml.model.score import PartCombineMode


CueMode = Literal["ignore", "include"]


@dataclass(frozen=True, slots=True)
class ExportOptions:
    partcombine_mode: PartCombineMode = "separate"
    cue_mode: CueMode = "ignore"

    @property
    def include_cues(self) -> bool:
        return self.cue_mode == "include"