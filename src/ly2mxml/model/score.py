"""Define the intermediate score model shared by conversion and serialization.

The dataclasses in this module intentionally sit between the LilyPond parser
tree and the MusicXML writer. They are rich enough to preserve the supported
musical semantics, but simpler than the original parser structure.
"""

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
    """Represent a resolved pitch in MusicXML-friendly components."""

    step: str
    octave: int
    alter: int = 0


@dataclass(frozen=True, slots=True)
class Direction:
    """Represent a musical direction attached to a note or measure position."""

    kind: DirectionKind
    value: str


@dataclass(frozen=True, slots=True)
class ClefChange:
    """Represent one clef change at a measure-relative musical offset."""

    offset: Fraction
    sign: str
    line: int
    octave_change: int | None = None


@dataclass(frozen=True, slots=True)
class Lyric:
    """Represent one lyric syllable attached to a note event."""

    text: str
    syllabic: LyricSyllabic | None = None
    extend: bool = False
    number: int | None = None


@dataclass(slots=True)
class MusicEvent:
    """Represent one resolved musical event inside a voice measure sequence."""

    duration: Fraction
    pitches: list[Pitch] = field(default_factory=list)
    is_rest: bool = False
    is_grace: bool = False
    grace_slash: bool = False
    is_cue: bool = False
    articulations: list[str] = field(default_factory=list)
    ornaments: list[str] = field(default_factory=list)
    fermatas: list[str] = field(default_factory=list)
    technical: list[str] = field(default_factory=list)
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
        """Return ``True`` when the event carries pitched note content."""

        return not self.is_rest and bool(self.pitches)


@dataclass(slots=True)
class Measure:
    """Collect the events and measure-level decorations for one measure."""

    number: int
    events: list[MusicEvent] = field(default_factory=list)
    duration: Fraction = Fraction(0, 1)
    clef_changes: list[ClefChange] = field(default_factory=list)
    right_barline: str | None = None


@dataclass(slots=True)
class Voice:
    """Hold a linearized stream of measures exported as one MusicXML voice."""

    id: str
    source_name: str
    measures: list[Measure] = field(default_factory=list)
    compress_empty_measures: bool = False


@dataclass(slots=True)
class Part:
    """Store staff-level defaults and the exported voices for one part."""

    id: str
    name: str
    short_name: str | None
    clef_sign: str
    clef_line: int
    time_signature: tuple[int, int]
    key_fifths: int
    key_mode: str
    clef_octave_change: int | None = None
    tempo_text: str | None = None
    voices: list[Voice] = field(default_factory=list)
    divisions: int = 1
    combine_group: str | None = None
    combine_member: int | None = None
    combined_name: str | None = None
    combined_short_name: str | None = None

    @property
    def measure_length(self) -> Fraction:
        """Return the measure duration implied by the current time signature."""

        numerator, denominator = self.time_signature
        return Fraction(numerator, denominator)


@dataclass(slots=True)
class ScoreMetadata:
    """Store score-level identification data emitted near the document header."""

    title: str | None = None
    composer: str | None = None
    arranger: str | None = None


@dataclass(slots=True)
class Score:
    """Represent the fully converted score together with conversion diagnostics."""

    metadata: ScoreMetadata
    parts: list[Part] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
