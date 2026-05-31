"""Unit tests for the Linearizer class.

Tests parse minimal inline LilyPond snippets via python-ly and exercise the
key flattening behaviours: note emission, grace note state, scaling/tuplets,
tremolo, repeat expansion, voice-separator split, tag filtering, barline and
ottava change detection, and duration estimation.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

import ly.document
import ly.music
from ly.music import items

from ly2mxml._types import (
    _BarlineChange,
    _OttavaChange,
    _PartialDuration,
    _RehearsalMark,
    _SecondaryVoiceBlocks,
    _WalkState,
)
from ly2mxml.linearizer import Linearizer, MUSICAL_NODE_TYPES
from ly2mxml.options import ExportOptions


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _FakeLoader:
    """Minimal loader that serves inline source text without touching the filesystem."""

    def __init__(self, text: str = "") -> None:
        self._text = text

    def read_text(self, path) -> str:  # noqa: ARG002
        return self._text


def _parse(source: str) -> items.Document:
    """Parse a LilyPond source string into a python-ly music tree."""
    doc = ly.document.Document(source, mode="lilypond")
    return ly.music.document(doc)


def _make_lz(source: str = "", include_cues: bool = True) -> Linearizer:
    """Return a Linearizer pre-loaded with *source* as fake source text."""
    loader = _FakeLoader(source)
    cache: dict[Path, str] = {}
    cue_mode = "include" if include_cues else "ignore"
    opts = ExportOptions(cue_mode=cue_mode)
    return Linearizer(loader, cache, opts)


def _music_block(source: str) -> items.MusicList:
    """Return the first top-level MusicList from a parsed snippet."""
    doc = _parse(source)
    for child in doc:
        if isinstance(child, items.MusicList):
            return child
        if isinstance(child, items.Score):
            for sc in child:
                if isinstance(sc, items.MusicList):
                    return sc
    raise AssertionError(f"No MusicList found in: {source!r}")


def _flatten(lz: Linearizer, node: items.Item, state: _WalkState | None = None):
    """Convenience: collect all flattened nodes from a music block."""
    return list(lz._iter_linear_nodes(node, state))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_musical_node_types(self) -> None:
        assert items.Note in MUSICAL_NODE_TYPES
        assert items.Rest in MUSICAL_NODE_TYPES
        assert items.Chord in MUSICAL_NODE_TYPES

    def test_musical_node_types_excludes_skip(self) -> None:
        # Skip is NOT a musical node (it's invisible rest)
        assert items.Skip not in MUSICAL_NODE_TYPES


# ---------------------------------------------------------------------------
# Basic note flattening
# ---------------------------------------------------------------------------


class TestBasicFlattening:
    def test_single_note_emits_one_node(self) -> None:
        src = "{ c'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert len(musical) == 1

    def test_two_notes_emit_two_note_nodes(self) -> None:
        src = "{ c'4 d'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert len(musical) == 2

    def test_rest_emitted(self) -> None:
        src = "{ r4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        rests = [n for n in nodes if isinstance(n.node, items.Rest)]
        assert len(rests) == 1

    def test_chord_emitted(self) -> None:
        src = "{ <c' e'>4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        chords = [n for n in nodes if isinstance(n.node, items.Chord)]
        assert len(chords) == 1

    def test_default_scale_is_one(self) -> None:
        src = "{ c'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert musical[0].scale == Fraction(1, 1)

    def test_not_grace_by_default(self) -> None:
        src = "{ c'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert musical[0].is_grace is False


# ---------------------------------------------------------------------------
# Grace note state propagation
# ---------------------------------------------------------------------------


class TestGraceNotePropagation:
    def test_acciaccatura_sets_grace_slash_true(self) -> None:
        src = r"{ \acciaccatura { e'8 } d'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        grace_nodes = [n for n in nodes if n.is_grace]
        assert len(grace_nodes) >= 1
        assert all(n.grace_slash for n in grace_nodes)

    def test_appoggiatura_grace_slash_false(self) -> None:
        src = r"{ \appoggiatura { f'8 } e'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        grace_nodes = [n for n in nodes if n.is_grace]
        assert len(grace_nodes) >= 1
        assert not any(n.grace_slash for n in grace_nodes)

    def test_non_grace_note_after_grace_not_marked(self) -> None:
        src = r"{ \acciaccatura { e'8 } d'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        non_grace = [n for n in nodes if isinstance(n.node, items.Note) and not n.is_grace]
        assert len(non_grace) >= 1


# ---------------------------------------------------------------------------
# Scaler / tuplet
# ---------------------------------------------------------------------------


class TestScalerTuplet:
    def test_tuplet_applies_scale_to_notes(self) -> None:
        src = r"{ \tuplet 3/2 { c'8 d'8 e'8 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert len(musical) == 3
        # Scale for 3/2 tuplet = 2/3
        for n in musical:
            assert n.scale == Fraction(2, 3)

    def test_tuplet_first_note_has_tuplet_start(self) -> None:
        src = r"{ \tuplet 3/2 { c'8 d'8 e'8 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert musical[0].tuplet_start is True

    def test_tuplet_last_note_has_tuplet_stop(self) -> None:
        src = r"{ \tuplet 3/2 { c'8 d'8 e'8 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert musical[-1].tuplet_stop is True


# ---------------------------------------------------------------------------
# Tremolo repeat
# ---------------------------------------------------------------------------


class TestTremoloRepeat:
    def test_single_note_tremolo_marks_single(self) -> None:
        src = r"{ \repeat tremolo 4 { c'16 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, MUSICAL_NODE_TYPES)]
        assert len(musical) >= 1
        assert musical[0].tremolo_type == "single"

    def test_single_note_tremolo_4_has_two_slashes(self) -> None:
        # repeat_count=4 → log2(4)=2 slashes
        src = r"{ \repeat tremolo 4 { c'16 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, MUSICAL_NODE_TYPES)]
        assert musical[0].tremolo_slashes == 2

    def test_two_note_tremolo_marks_start_stop(self) -> None:
        src = r"{ \repeat tremolo 4 { c'16 d'16 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, MUSICAL_NODE_TYPES)]
        types = [n.tremolo_type for n in musical]
        assert "start" in types
        assert "stop" in types


# ---------------------------------------------------------------------------
# Repeat expansion
# ---------------------------------------------------------------------------


class TestRepeatExpansion:
    def test_unfold_repeat_doubles_notes(self) -> None:
        src = r"{ \repeat unfold 2 { c'4 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert len(musical) == 2

    def test_volta_repeat_emits_both_iterations(self) -> None:
        src = r"{ \repeat volta 2 { c'4 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        assert len(musical) == 2

    def test_volta_with_alternatives(self) -> None:
        src = r"{ \repeat volta 2 { c'4 } \alternative { { d'4 } { e'4 } } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        musical = [n for n in nodes if isinstance(n.node, items.Note)]
        # 2 body iterations + 2 alternative endings = 4
        assert len(musical) == 4


# ---------------------------------------------------------------------------
# Voice separator / simultaneous split
# ---------------------------------------------------------------------------


class TestVoiceSeparatorSplit:
    def test_voice_separator_emits_secondary_voice_blocks_marker(self) -> None:
        src = r"{ << { c'4 } \\ { e'4 } >> }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        markers = [n for n in nodes if isinstance(n.node, _SecondaryVoiceBlocks)]
        assert len(markers) == 1

    def test_voice_separator_first_voice_notes_emitted_directly(self) -> None:
        src = r"{ << { c'4 } \\ { e'4 } >> }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        note_nodes = [n for n in nodes if isinstance(n.node, items.Note)]
        # Only the first voice is flattened; second is in SecondaryVoiceBlocks
        assert len(note_nodes) == 1

    def test_secondary_voice_blocks_contains_remaining_blocks(self) -> None:
        src = r"{ << { c'4 } \\ { e'4 } \\ { g'4 } >> }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        markers = [n for n in nodes if isinstance(n.node, _SecondaryVoiceBlocks)]
        assert len(markers) == 1
        # Two remaining blocks (second and third voices)
        assert len(markers[0].node.blocks) == 2


# ---------------------------------------------------------------------------
# Barline change detection
# ---------------------------------------------------------------------------


class TestBarlineChangeDetection:
    def test_bar_command_emits_barline_change(self) -> None:
        src = r'{ c1 \bar "||" d1 }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        barlines = [n for n in nodes if isinstance(n.node, _BarlineChange)]
        assert len(barlines) == 1

    def test_bar_command_value_correct(self) -> None:
        src = r'{ c1 \bar "||" d1 }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        barlines = [n for n in nodes if isinstance(n.node, _BarlineChange)]
        assert barlines[0].node.value == "||"

    def test_final_barline_detected(self) -> None:
        src = r'{ c1 \bar "|." }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        barlines = [n for n in nodes if isinstance(n.node, _BarlineChange)]
        assert len(barlines) == 1
        assert barlines[0].node.value == "|."


# ---------------------------------------------------------------------------
# Ottava change detection
# ---------------------------------------------------------------------------


class TestOttavaChangeDetection:
    def test_ottava_emits_ottava_change(self) -> None:
        src = r'{ \ottava #1 c1 \ottava #0 }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        ottava_nodes = [n for n in nodes if isinstance(n.node, _OttavaChange)]
        assert len(ottava_nodes) == 2

    def test_ottava_up_value_one(self) -> None:
        src = r'{ \ottava #1 c1 }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        ottava_nodes = [n for n in nodes if isinstance(n.node, _OttavaChange)]
        assert ottava_nodes[0].node.value == 1

    def test_ottava_stop_value_zero(self) -> None:
        src = r'{ \ottava #1 c1 \ottava #0 }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        ottava_nodes = [n for n in nodes if isinstance(n.node, _OttavaChange)]
        stop = [n for n in ottava_nodes if n.node.value == 0]
        assert len(stop) == 1


# ---------------------------------------------------------------------------
# Rehearsal mark detection
# ---------------------------------------------------------------------------


class TestRehearsalMarkDetection:
    def test_mark_default_emits_rehearsal_mark(self) -> None:
        src = r'{ \mark \default c1 }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        marks = [n for n in nodes if isinstance(n.node, _RehearsalMark)]
        assert len(marks) == 1

    def test_mark_default_label_is_none(self) -> None:
        src = r'{ \mark \default c1 }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        marks = [n for n in nodes if isinstance(n.node, _RehearsalMark)]
        assert marks[0].node.label is None

    def test_mark_string_label(self) -> None:
        src = r'{ \mark "A" c1 }'
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        marks = [n for n in nodes if isinstance(n.node, _RehearsalMark)]
        assert len(marks) == 1
        assert marks[0].node.label == "A"


# ---------------------------------------------------------------------------
# Partial measure detection
# ---------------------------------------------------------------------------


class TestPartialMeasureDetection:
    def test_partial_emits_partial_duration(self) -> None:
        src = r"{ \partial 4 c'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        partials = [n for n in nodes if isinstance(n.node, _PartialDuration)]
        assert len(partials) == 1

    def test_partial_quarter_duration(self) -> None:
        src = r"{ \partial 4 c'4 }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        partials = [n for n in nodes if isinstance(n.node, _PartialDuration)]
        assert partials[0].node.duration == Fraction(1, 4)


# ---------------------------------------------------------------------------
# Tag filtering
# ---------------------------------------------------------------------------


class TestTagFiltering:
    def test_removeWithTag_excludes_tagged_content(self) -> None:
        src = r"{ \tag #'skip { c'4 } d'4 }"
        lz = _make_lz()
        block = _music_block(src)
        state = _WalkState(removed_tags=frozenset({"skip"}))
        nodes = _flatten(lz, block, state)
        note_nodes = [n for n in nodes if isinstance(n.node, items.Note)]
        # Only d' should appear — c' is in the removed tag
        assert len(note_nodes) == 1

    def test_keepWithTag_includes_tagged_content(self) -> None:
        src = r"{ \tag #'keep { c'4 } \tag #'skip { d'4 } }"
        lz = _make_lz()
        block = _music_block(src)
        state = _WalkState(keep_tags=frozenset({"keep"}))
        nodes = _flatten(lz, block, state)
        note_nodes = [n for n in nodes if isinstance(n.node, items.Note)]
        # Only c' is in the kept tag
        assert len(note_nodes) == 1

    def test_no_tag_filter_includes_all(self) -> None:
        src = r"{ \tag #'a { c'4 } \tag #'b { d'4 } }"
        lz = _make_lz()
        block = _music_block(src)
        nodes = _flatten(lz, block)
        note_nodes = [n for n in nodes if isinstance(n.node, items.Note)]
        assert len(note_nodes) == 2


# ---------------------------------------------------------------------------
# Duration estimation
# ---------------------------------------------------------------------------


class TestDurationEstimation:
    def test_single_quarter_note_duration(self) -> None:
        src = "{ c'4 }"
        lz = _make_lz()
        block = _music_block(src)
        dur = lz._duration_of_music(block)
        assert dur == Fraction(1, 4)

    def test_two_quarter_notes_duration(self) -> None:
        src = "{ c'4 d'4 }"
        lz = _make_lz()
        block = _music_block(src)
        dur = lz._duration_of_music(block)
        assert dur == Fraction(1, 2)

    def test_half_note_duration(self) -> None:
        src = "{ c'2 }"
        lz = _make_lz()
        block = _music_block(src)
        dur = lz._duration_of_music(block)
        assert dur == Fraction(1, 2)

    def test_whole_note_duration(self) -> None:
        src = "{ c'1 }"
        lz = _make_lz()
        block = _music_block(src)
        dur = lz._duration_of_music(block)
        assert dur == Fraction(1, 1)

    def test_simultaneous_takes_maximum(self) -> None:
        # Simultaneous blocks: max duration wins
        src = "{ << { c'1 } { d'2 } >> }"
        lz = _make_lz()
        block = _music_block(src)
        dur = lz._duration_of_music(block)
        assert dur == Fraction(1, 1)

    def test_grace_notes_contribute_zero_duration(self) -> None:
        src = r"{ \acciaccatura { e'8 } d'4 }"
        lz = _make_lz()
        block = _music_block(src)
        dur = lz._duration_of_music(block)
        assert dur == Fraction(1, 4)


# ---------------------------------------------------------------------------
# Duration-from-node helper
# ---------------------------------------------------------------------------


class TestDurationFromNode:
    def test_quarter_note_duration(self) -> None:
        lz = _make_lz()
        dur = lz._duration_from_node((Fraction(1, 4), Fraction(1, 1)))
        assert dur == Fraction(1, 4)

    def test_dotted_quarter_duration(self) -> None:
        lz = _make_lz()
        # dotted quarter: base=1/4, scaling=3/2
        dur = lz._duration_from_node((Fraction(1, 4), Fraction(3, 2)))
        assert dur == Fraction(3, 8)

    def test_scale_applied(self) -> None:
        lz = _make_lz()
        dur = lz._duration_from_node((Fraction(1, 4), Fraction(1, 1)), scale=Fraction(2, 3))
        assert dur == Fraction(1, 6)

    def test_full_measure_rest_uses_measure_length(self) -> None:
        lz = _make_lz()
        dur = lz._duration_from_node(
            (Fraction(1, 1), Fraction(1, 1)),
            token="R",
            measure_length=Fraction(3, 4),
        )
        assert dur == Fraction(3, 4)


# ---------------------------------------------------------------------------
# _split_voice_separator_block
# ---------------------------------------------------------------------------


class TestSplitVoiceSeparatorBlock:
    def test_simultaneous_block_with_separator_returns_two_sublists(self) -> None:
        src = r"<< { c'4 } \\ { e'4 } >>"
        lz = _make_lz()
        doc = _parse(src)
        simultaneous = next(
            (child for child in doc if isinstance(child, items.MusicList) and child.simultaneous),
            None,
        )
        if simultaneous is None:
            pytest.skip("Parser did not produce a top-level simultaneous MusicList")
        result = lz._split_voice_separator_block(simultaneous)
        assert result is not None
        assert len(result) == 2

    def test_simultaneous_context_block_returns_none(self) -> None:
        # A simultaneous block with \\new Context returns None (not a << \\ >> shorthand)
        src = r"<< \new Staff { c'4 } \new Staff { e'4 } >>"
        lz = _make_lz()
        doc = _parse(src)
        simultaneous = next(
            (child for child in doc if isinstance(child, items.MusicList) and child.simultaneous),
            None,
        )
        if simultaneous is None:
            pytest.skip("Parser did not produce a top-level simultaneous MusicList")
        result = lz._split_voice_separator_block(simultaneous)
        assert result is None


# ---------------------------------------------------------------------------
# _extract_text helper
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_extract_string_node(self) -> None:
        src = r'{ \bar "||" c1 }'
        lz = _make_lz()
        doc = _parse(src)
        strings = [
            child
            for block in doc
            for child in block
            if isinstance(child, items.String)
        ]
        if not strings:
            pytest.skip("No String nodes found in parsed snippet")
        text = lz._extract_text(strings[0])
        assert text == "||"

    def test_extract_none_returns_none(self) -> None:
        lz = _make_lz()
        assert lz._extract_text(None) is None
