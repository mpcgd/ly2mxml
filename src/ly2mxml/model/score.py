from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

from ly2mxml.diagnostics import Diagnostic


DirectionKind = Literal["dynamic", "words", "tempo", "wedge", "octave-shift"]
LyricSyllabic = Literal["single", "begin", "middle", "end"]
PartCombineMode = Literal["separate", "combined"]


@dataclass(frozen=True, slots=True)
class Pitch:
    step: str
    octave: int
    alter: int = 0


@dataclass(frozen=True, slots=True)
class Direction:
    kind: DirectionKind
    value: str


@dataclass(frozen=True, slots=True)
class Lyric:
    text: str
    syllabic: LyricSyllabic | None = None
    extend: bool = False
    number: int | None = None


@dataclass(slots=True)
class MusicEvent:
    duration: Fraction
    pitches: list[Pitch] = field(default_factory=list)
    is_rest: bool = False
    is_grace: bool = False
    grace_slash: bool = False
    is_cue: bool = False
    articulations: list[str] = field(default_factory=list)
    ornaments: list[str] = field(default_factory=list)
    directions: list[Direction] = field(default_factory=list)
    slur_start_count: int = 0
    slur_stop_count: int = 0
    tie_start: bool = False
    tie_stop: bool = False
    time_modification: tuple[int, int] | None = None
    tuplet_start: bool = False
    tuplet_stop: bool = False
    lyrics: list[Lyric] = field(default_factory=list)

    @property
    def is_note(self) -> bool:
        return not self.is_rest and bool(self.pitches)


@dataclass(slots=True)
class Measure:
    number: int
    events: list[MusicEvent] = field(default_factory=list)
    duration: Fraction = Fraction(0, 1)
    right_barline: str | None = None


@dataclass(slots=True)
class Voice:
    id: str
    source_name: str
    measures: list[Measure] = field(default_factory=list)
    compress_empty_measures: bool = False


@dataclass(slots=True)
class Part:
    id: str
    name: str
    short_name: str | None
    clef_sign: str
    clef_line: int
    time_signature: tuple[int, int]
    key_fifths: int
    key_mode: str
    tempo_text: str | None = None
    voices: list[Voice] = field(default_factory=list)
    divisions: int = 1
    combine_group: str | None = None
    combine_member: int | None = None
    combined_name: str | None = None
    combined_short_name: str | None = None

    @property
    def measure_length(self) -> Fraction:
        numerator, denominator = self.time_signature
        return Fraction(numerator, denominator)


@dataclass(slots=True)
class ScoreMetadata:
    title: str | None = None
    composer: str | None = None
    arranger: str | None = None


@dataclass(slots=True)
class Score:
    metadata: ScoreMetadata
    parts: list[Part] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
