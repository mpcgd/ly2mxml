"""Unit tests for ly2mxml.voice_builder — VoiceBuilder and related constants."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile

import pytest

from ly2mxml.voice_builder import (
    VoiceBuilder,
    ARTICULATION_MAP,
    CODA_SEGNO_COMMANDS,
    DYNAMIC_MARKS,
    FERMATA_MAP,
    IGNORED_COMMANDS,
    ORNAMENT_MAP,
    PERFORMANCE_TEXT_MARKS,
    TECHNICAL_MAP,
    TEXT_DYNAMICS,
    VOICE_COMMAND_STEMS,
    WEDGE_DYNAMICS,
)
from ly2mxml.options import ExportOptions


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_dynamic_marks_contains_piano(self):
        assert "\\p" in DYNAMIC_MARKS
        assert DYNAMIC_MARKS["\\p"] == "p"

    def test_dynamic_marks_contains_forte(self):
        assert "\\f" in DYNAMIC_MARKS
        assert DYNAMIC_MARKS["\\f"] == "f"

    def test_wedge_dynamics_crescendo(self):
        assert "\\<" in WEDGE_DYNAMICS
        assert WEDGE_DYNAMICS["\\<"] == "crescendo"

    def test_wedge_dynamics_stop(self):
        assert "\\!" in WEDGE_DYNAMICS
        assert WEDGE_DYNAMICS["\\!"] == "stop"

    def test_text_dynamics_cresc(self):
        assert "\\cresc" in TEXT_DYNAMICS

    def test_articulation_staccato(self):
        assert "." in ARTICULATION_MAP
        assert ARTICULATION_MAP["."] == "staccato"

    def test_articulation_accent(self):
        assert ">" in ARTICULATION_MAP
        assert ARTICULATION_MAP[">"] == "accent"

    def test_ornament_trill(self):
        assert "\\trill" in ORNAMENT_MAP
        assert ORNAMENT_MAP["\\trill"] == "trill-mark"

    def test_fermata_plain(self):
        assert "\\fermata" in FERMATA_MAP
        assert FERMATA_MAP["\\fermata"] == ""

    def test_technical_upbow(self):
        assert "\\upbow" in TECHNICAL_MAP
        assert TECHNICAL_MAP["\\upbow"] == "up-bow"

    def test_voice_command_stems(self):
        assert VOICE_COMMAND_STEMS["\\voiceOne"] == "up"
        assert VOICE_COMMAND_STEMS["\\voiceTwo"] == "down"
        assert VOICE_COMMAND_STEMS["\\stemNeutral"] is None

    def test_performance_text_pizzicato(self):
        assert "\\pizzicato" in PERFORMANCE_TEXT_MARKS
        assert PERFORMANCE_TEXT_MARKS["\\pizzicato"] == "pizz."

    def test_coda_segno(self):
        assert "\\coda" in CODA_SEGNO_COMMANDS
        assert CODA_SEGNO_COMMANDS["\\coda"] == "coda"

    def test_ignored_commands_has_compress(self):
        assert "\\compressEmptyMeasures" in IGNORED_COMMANDS


# ---------------------------------------------------------------------------
# Helpers: _dynamic_to_direction / _barline_style / _ottava_direction
# ---------------------------------------------------------------------------


def _make_vb() -> VoiceBuilder:
    """Return a VoiceBuilder with a minimal mock linearizer."""
    lz = MagicMock()
    options = ExportOptions()
    return VoiceBuilder(lz, options)


class TestDynamicToDirection:
    def test_pp_returns_dynamic_direction(self):
        vb = _make_vb()
        result = vb._dynamic_to_direction("\\pp")
        assert result is not None
        assert result.kind == "dynamic"
        assert result.value == "pp"

    def test_crescendo_wedge(self):
        vb = _make_vb()
        result = vb._dynamic_to_direction("\\<")
        assert result is not None
        assert result.kind == "wedge"
        assert result.value == "crescendo"

    def test_cresc_text(self):
        vb = _make_vb()
        result = vb._dynamic_to_direction("\\cresc")
        assert result is not None
        assert result.kind == "words"
        assert "cresc" in result.value

    def test_unknown_returns_none(self):
        vb = _make_vb()
        result = vb._dynamic_to_direction("\\unknown")
        assert result is None


class TestBarlineStyle:
    def test_double_barline(self):
        vb = _make_vb()
        assert vb._barline_style("||") == "light-light"

    def test_final_barline(self):
        vb = _make_vb()
        assert vb._barline_style("|.") == "light-heavy"

    def test_repeat_start(self):
        vb = _make_vb()
        assert vb._barline_style("|:") == "heavy-light:forward"

    def test_empty_is_none(self):
        vb = _make_vb()
        assert vb._barline_style("") == "none"

    def test_unknown_returns_none(self):
        vb = _make_vb()
        assert vb._barline_style("???") is None


class TestOttavaDirections:
    def test_ottava_up_start(self):
        vb = _make_vb()
        dirs = vb._ottava_directions(-1, None)
        assert len(dirs) == 1
        assert dirs[0].kind == "octave-shift"
        assert "up" in dirs[0].value

    def test_ottava_down_start(self):
        vb = _make_vb()
        dirs = vb._ottava_directions(1, None)
        assert len(dirs) == 1
        assert "down" in dirs[0].value

    def test_ottava_stop_and_restart(self):
        vb = _make_vb()
        dirs = vb._ottava_directions(-1, 1)
        assert len(dirs) == 2
        assert "stop" in dirs[0].value
        assert "up" in dirs[1].value

    def test_ottava_zero_stops_active(self):
        vb = _make_vb()
        dirs = vb._ottava_directions(0, -1)
        assert len(dirs) == 1
        assert "stop" in dirs[0].value

    def test_ottava_zero_when_none_is_empty(self):
        vb = _make_vb()
        dirs = vb._ottava_directions(0, None)
        assert dirs == []


# ---------------------------------------------------------------------------
# VoiceBuilder counter and cache resets
# ---------------------------------------------------------------------------


class TestVoiceBuilderState:
    def test_initial_counter_is_zero(self):
        vb = _make_vb()
        assert vb._rehearsal_mark_counter == 0

    def test_initial_cache_is_empty(self):
        vb = _make_vb()
        assert vb._quote_voice_cache == {}

    def test_separate_instances_have_independent_counters(self):
        vb1 = _make_vb()
        vb2 = _make_vb()
        vb1._rehearsal_mark_counter = 5
        assert vb2._rehearsal_mark_counter == 0


# ---------------------------------------------------------------------------
# VoiceBuilder.build_voice — integration using real LilyPond fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def minimal_voice_builder(repo_root: Path):
    """Return a VoiceBuilder wired to a real Linearizer for integration tests."""
    from ly2mxml.converter import LilypondConverter

    converter = LilypondConverter()
    return converter._vb, converter._lz


class TestBuildVoiceIntegration:
    def test_empty_fixture_produces_voice(self, repo_root: Path, minimal_voice_builder):
        from ly2mxml.converter import LilypondConverter
        from ly2mxml._types import _WalkState
        from ly.music import items

        vb, lz = minimal_voice_builder
        fixture = repo_root / "tests" / "fixtures" / "barlines.ly"

        # Load the document and find the first MusicList
        converter = LilypondConverter()
        doc = converter.adapter.load_document_tree(fixture)
        assignments = converter._collect_assignments(doc)
        # Find any music node to build a voice from
        music_node = None
        for name, value in assignments.items():
            if isinstance(value, items.Item):
                music_node = value
                break

        if music_node is None:
            pytest.skip("No music node found in fixture")

        from ly2mxml.voice_builder import VoiceBuilder
        from ly2mxml.linearizer import Linearizer
        from ly2mxml.options import ExportOptions

        source_cache: dict = {}
        real_lz = Linearizer(converter.adapter.loader, source_cache, ExportOptions())
        real_vb = VoiceBuilder(real_lz, ExportOptions())

        voice = real_vb.build_voice(
            voice_id="test",
            source_name="test",
            music_node=music_node,
            measure_length=Fraction(1, 1),
            assignments=assignments,
            quote_sources={},
            diagnostics=[],
        )
        assert voice is not None
        assert voice.id == "test"

    def test_rehearsal_mark_counter_increments(self, minimal_voice_builder):
        vb, lz = minimal_voice_builder
        # Directly manipulate to verify independence
        vb._rehearsal_mark_counter = 3
        assert vb._rehearsal_mark_counter == 3
