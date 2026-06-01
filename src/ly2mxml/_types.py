"""Shared internal dataclasses for the LilyPond converter pipeline.

All mutable and frozen dataclasses that are shared between the converter
orchestration layer, the linearizer traversal, and the voice builder live here
so that each module can import them without creating circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from ly.music import items

from ly2mxml.model.score import Direction, Measure, MusicEvent


# ---------------------------------------------------------------------------
# Lightweight state carried during AST traversal / flattening
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _GlobalSettings:
    time_signature: tuple[int, int] = (4, 4)
    key_fifths: int = 0
    key_mode: str = "major"
    tempo_text: str | None = None


@dataclass(frozen=True, slots=True)
class _TransposeSpec:
    octave: int
    steps: int
    alter: Fraction


@dataclass(frozen=True, slots=True)
class _WalkState:
    """Track contextual conversion state while flattening LilyPond nodes."""

    is_grace: bool = False
    grace_slash: bool = False
    auto_grace_slur: bool = False
    scale: Fraction = Fraction(1, 1)
    cues_killed: bool = False
    allow_cues: bool = True
    removed_tags: frozenset[str] = frozenset()
    keep_tags: frozenset[str] = frozenset()
    transpose_specs: tuple[_TransposeSpec, ...] = ()
    relative_reference: object | None = None
    measure_length: Fraction | None = None


@dataclass(frozen=True, slots=True)
class _SequenceFilterResult:
    emitted: tuple[tuple[items.Item, _WalkState], ...]
    remaining_state: _WalkState
    consumed: int


# ---------------------------------------------------------------------------
# Marker / event types yielded by the linearizer
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _CueInsertion:
    quote_name: str
    duration: Fraction
    source_node: items.Item
    suppressed: bool


@dataclass(frozen=True, slots=True)
class _OttavaChange:
    value: int
    source_node: items.Item


@dataclass(frozen=True, slots=True)
class _BarlineChange:
    value: str
    source_node: items.Item


@dataclass(frozen=True, slots=True)
class _RehearsalMark:
    label: str | None  # None means auto-number from converter counter
    source_node: items.Item


@dataclass(frozen=True, slots=True)
class _PartialDuration:
    """Represent a \\partial directive with its effective measure duration."""

    duration: Fraction
    source_node: items.Item


@dataclass(frozen=True, slots=True)
class _SecondaryVoiceBlocks:
    """Carry secondary sub-blocks from a mid-stream simultaneous expansion.

    When ``<< {v1} \\\\ {v2} >>`` appears inside a sequential voice stream,
    ``_iter_linear_nodes`` expands the primary sub-block inline and yields this
    marker so that ``_build_voice`` can build the remaining sub-blocks as extra
    voices appended to the part alongside the primary voice.
    """

    blocks: tuple[items.MusicList, ...]
    walk_state: _WalkState
    source_node: items.MusicList


@dataclass(frozen=True, slots=True)
class _NewContextCommand:
    context_type: str
    context_id: str | None
    content_node: items.Item
    consumed: int


@dataclass(slots=True)
class _FlattenedNode:
    """Carry one flattened node together with the state needed to render it."""

    node: items.Item | _CueInsertion | _OttavaChange | _BarlineChange | _RehearsalMark | _PartialDuration | _SecondaryVoiceBlocks
    is_grace: bool
    grace_slash: bool
    auto_grace_slur: bool
    scale: Fraction
    transpose_specs: tuple[_TransposeSpec, ...] = ()
    time_modification: tuple[int, int] | None = None
    tuplet_start: bool = False
    tuplet_stop: bool = False
    tremolo_type: str = ""
    tremolo_slashes: int = 0
    resolved_pitches: tuple[object, ...] = ()


# ---------------------------------------------------------------------------
# Voice / staff planning types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _VoiceReference:
    name: str
    state: _WalkState
    context_id: str | None = None
    music_node: items.Item | None = None

    @property
    def lyric_target(self) -> str:
        return self.context_id or self.name


@dataclass(frozen=True, slots=True)
class _PartCombinePlan:
    voice_refs: tuple[_VoiceReference, ...]
    names: tuple[str, ...]
    short_names: tuple[str | None, ...]
    group_id: str


@dataclass(frozen=True, slots=True)
class _PartBuildContext:
    staff_index: int
    name: str | None
    short_name: str | None
    clef_sign: str
    clef_line: int
    clef_octave_change: int | None
    global_settings: _GlobalSettings


@dataclass(frozen=True, slots=True)
class _StaffPartPlan:
    part_context: _PartBuildContext
    voice_refs: tuple[_VoiceReference, ...]
    partcombine_groups: tuple[_PartCombinePlan, ...]
    lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]]


@dataclass(slots=True)
class _StaffPlanningState:
    global_ref: _VoiceReference
    voice_refs: list[_VoiceReference] = field(default_factory=list)
    partcombine_groups: list[_PartCombinePlan] = field(default_factory=list)
    lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]] = field(default_factory=dict)
    last_voice_ref: _VoiceReference | None = None


# ---------------------------------------------------------------------------
# Voice-building state
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _VoiceBuildState:
    """Track measure assembly state while building one exported voice."""

    current_measure: Measure
    elapsed: Fraction = Fraction(0, 1)
    timeline_position: Fraction = Fraction(0, 1)
    # Intentionally not importing DEFAULT_CLEF here to avoid a dep on
    # state_resolver at import time; the converter sets the default explicitly.
    current_clef: tuple[str, int, int | None] = ("G", 2, None)
    pending_directions: list[Direction] = field(default_factory=list)
    last_event: MusicEvent | None = None
    attachment_event: MusicEvent | None = None
    pending_tie_signature: tuple[tuple[str, int, int], ...] | None = None
    pending_grace_slur_stop: bool = False
    active_ottava: int | None = None
    current_key_fifths: int = 0
    current_key_mode: str = "major"
    current_time_signature: tuple[int, int] = (4, 4)
    pending_glissando_stop: bool = False
    current_stem: str | None = None


@dataclass(frozen=True, slots=True)
class _LyricToken:
    kind: str
    text: str | None = None
