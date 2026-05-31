"""Pure pitch, clef, key, and duration resolution helpers.

All functions are stateless: they operate only on their explicit arguments and
the module-level lookup tables.  They are placed here so they can be imported
by the linearizer, the voice builder, and the converter without circular
dependencies, and so they can be unit-tested independently of the full
conversion pipeline.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import TYPE_CHECKING

from ly.music import items

if TYPE_CHECKING:
    # Only needed for type annotations; avoid a circular import at runtime.
    from ly2mxml._types import (
        _FlattenedNode,
        _TransposeSpec,
        _WalkState,
    )

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

DEFAULT_CLEF: tuple[str, int, None] = ("G", 2, None)

CLEF_MAP: dict[str, tuple[str, int, int | None]] = {
    "treble": DEFAULT_CLEF,
    "violin": DEFAULT_CLEF,
    "treble_8": ("G", 2, -1),
    "treble^8": ("G", 2, 1),
    "treble_15": ("G", 2, -2),
    "treble^15": ("G", 2, 2),
    "soprano": ("C", 1, None),
    "mezzosoprano": ("C", 2, None),
    "mezzo-soprano": ("C", 2, None),
    "alto": ("C", 3, None),
    "tenor": ("C", 4, None),
    "baritone": ("C", 5, None),
    "bass": ("F", 4, None),
    "bass_8": ("F", 4, -1),
    "bass^8": ("F", 4, 1),
    "bass_15": ("F", 4, -2),
    "bass^15": ("F", 4, 2),
    "percussion": ("percussion", 2, None),
}

STEP_MAP: dict[int, str] = {
    0: "C",
    1: "D",
    2: "E",
    3: "F",
    4: "G",
    5: "A",
    6: "B",
}

KEY_FIFTHS: dict[tuple[int, int, str], int] = {
    (0, 0, "major"): 0,
    (4, 0, "major"): 1,
    (1, 0, "major"): 2,
    (5, 0, "major"): 3,
    (2, 0, "major"): 4,
    (6, 0, "major"): 5,
    (3, 1, "major"): 6,
    (0, 1, "major"): 7,
    (3, 0, "major"): -1,
    (6, -1, "major"): -2,
    (2, -1, "major"): -3,
    (5, -1, "major"): -4,
    (1, -1, "major"): -5,
    (4, -1, "major"): -6,
    (0, -1, "major"): -7,
    (5, 0, "minor"): 0,
    (2, 0, "minor"): 1,
    (6, 0, "minor"): 2,
    (3, 1, "minor"): 3,
    (0, 1, "minor"): 4,
    (4, 1, "minor"): 5,
    (1, 1, "minor"): 6,
    (5, 1, "minor"): 7,
    (1, 0, "minor"): -1,
    (4, 0, "minor"): -2,
    (0, 0, "minor"): -3,
    (3, 0, "minor"): -4,
    (6, -1, "minor"): -5,
    (2, -1, "minor"): -6,
    (5, -1, "minor"): -7,
}

# Chromatic semitone values for each diatonic scale degree (C=0, D=2, …, B=11)
PITCH_SCALE: tuple[Fraction, ...] = (
    Fraction(0, 1),
    Fraction(2, 1),
    Fraction(4, 1),
    Fraction(5, 1),
    Fraction(7, 1),
    Fraction(9, 1),
    Fraction(11, 1),
)

BEAT_UNIT_MAP: dict[Fraction, str] = {
    Fraction(1, 1): "whole",
    Fraction(1, 2): "half",
    Fraction(1, 4): "quarter",
    Fraction(1, 8): "eighth",
    Fraction(1, 16): "16th",
    Fraction(1, 32): "32nd",
    Fraction(1, 64): "64th",
}

# ---------------------------------------------------------------------------
# Pitch helpers
# ---------------------------------------------------------------------------


def copy_pitch(raw_pitch: object) -> object:
    """Return a copy of a python-ly pitch object."""
    return raw_pitch.copy() if hasattr(raw_pitch, "copy") else raw_pitch


def resolve_relative_pitch(raw_pitch: object, reference_pitch: object | None) -> object:
    """Resolve a LilyPond relative pitch against the current reference."""
    pitch = copy_pitch(raw_pitch)
    if reference_pitch is not None:
        pitch.makeAbsolute(reference_pitch)  # type: ignore[attr-defined]
    return pitch


def resolve_relative_chord(
    node: items.Chord,
    reference_pitch: object | None,
) -> tuple[object, ...]:
    """Resolve all notes in a chord against the current relative reference."""
    resolved: list[object] = []
    current_reference = reference_pitch
    for child in node:
        if not isinstance(child, items.Note):
            continue
        pitch = resolve_relative_pitch(child.pitch, current_reference)
        resolved.append(pitch)
        current_reference = pitch
    return tuple(resolved)


def pitch_components(
    raw_pitch: object,
    transpose_specs: tuple["_TransposeSpec", ...] = (),
) -> tuple[int, int, int]:
    """Return *(note_index, alter, absolute_octave)* for a pitch after transposition."""
    note = int(getattr(raw_pitch, "note", 0))
    alter = Fraction(getattr(raw_pitch, "alter", 0))
    octave = int(getattr(raw_pitch, "octave", 0))
    for spec in transpose_specs:
        note, alter, octave = apply_transpose_spec(note, alter, octave, spec)
    return note, int(alter), octave + 4


def to_pitch(raw_pitch: object, transpose_specs: tuple["_TransposeSpec", ...] = ()) -> "Pitch":  # noqa: F821
    """Convert a raw python-ly pitch to the internal :class:`~ly2mxml.model.score.Pitch`."""
    from ly2mxml.model.score import Pitch

    note, alter, octave = pitch_components(raw_pitch, transpose_specs)
    return Pitch(step=STEP_MAP[note], alter=alter, octave=octave)


def make_transpose_spec(from_pitch: object, to_pitch: object) -> "_TransposeSpec":
    """Build a :class:`~ly2mxml.converter._TransposeSpec` from two python-ly pitches."""
    from ly2mxml.converter import _TransposeSpec

    from_note = int(getattr(from_pitch, "note", 0))
    to_note = int(getattr(to_pitch, "note", 0))
    from_alter = Fraction(getattr(from_pitch, "alter", 0))
    to_alter = Fraction(getattr(to_pitch, "alter", 0))
    from_octave = int(getattr(from_pitch, "octave", 0))
    to_octave = int(getattr(to_pitch, "octave", 0))
    return _TransposeSpec(
        octave=to_octave - from_octave,
        steps=to_note - from_note,
        alter=PITCH_SCALE[to_note] + to_alter - PITCH_SCALE[from_note] - from_alter,
    )


def apply_transpose_spec(
    note: int,
    alter: Fraction,
    octave: int,
    spec: "_TransposeSpec",
) -> tuple[int, Fraction, int]:
    """Apply one transposition spec and return the adjusted *(note, alter, octave)*."""
    doct, transposed_note = divmod(note + spec.steps, 7)
    transposed_alter = alter + spec.alter - doct * 12 - PITCH_SCALE[transposed_note] + PITCH_SCALE[note]
    transposed_octave = octave + spec.octave + doct

    while transposed_alter > 1:
        doct, next_note = divmod(transposed_note + 1, 7)
        transposed_alter -= doct * 12 + PITCH_SCALE[next_note] - PITCH_SCALE[transposed_note]
        transposed_octave += doct
        transposed_note = next_note
    while transposed_alter < -1:
        doct, next_note = divmod(transposed_note - 1, 7)
        transposed_alter += doct * -12 + PITCH_SCALE[transposed_note] - PITCH_SCALE[next_note]
        transposed_octave += doct
        transposed_note = next_note

    return transposed_note, transposed_alter, transposed_octave


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def key_fifths(
    pitch: object | None,
    mode: str,
    transpose_specs: tuple["_TransposeSpec", ...] = (),
) -> int:
    """Return the ``<fifths>`` value for a LilyPond key signature."""
    if pitch is None:
        return 0
    note, alter, _ = pitch_components(pitch, transpose_specs)
    return KEY_FIFTHS.get((note, alter, mode), 0)


# ---------------------------------------------------------------------------
# Clef helpers
# ---------------------------------------------------------------------------


def resolve_clef(clef_name: str | None) -> tuple[str, int, int | None] | None:
    """Resolve a LilyPond clef specifier to *(sign, line, octave_change)*."""
    if not clef_name:
        return None
    normalized = clef_name.strip().strip('"').lower().replace(" ", "")
    normalized = {"mezzo-soprano": "mezzosoprano"}.get(normalized, normalized)
    return CLEF_MAP.get(normalized)


# ---------------------------------------------------------------------------
# Grace note helpers
# ---------------------------------------------------------------------------


def grace_has_slash(node: items.Grace) -> bool:
    """Return ``True`` when *node* is an acciaccatura (slashed grace)."""
    return str(getattr(node, "token", "")) == "\\acciaccatura"


# ---------------------------------------------------------------------------
# Advance relative-pitch walk state
# ---------------------------------------------------------------------------


def advance_relative_state(
    state: "_WalkState",
    flattened: "_FlattenedNode",
) -> "_WalkState":
    """Return an updated walk state with the last resolved pitch as new reference."""
    if state.relative_reference is None or not flattened.resolved_pitches:
        return state
    if isinstance(flattened.node, items.Chord):
        next_reference = flattened.resolved_pitches[0]
    else:
        next_reference = flattened.resolved_pitches[-1]
    return replace(state, relative_reference=copy_pitch(next_reference))
