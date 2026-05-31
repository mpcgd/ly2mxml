"""Unit tests for ly2mxml.state_resolver — pure pitch, clef, key resolution."""

from __future__ import annotations

from fractions import Fraction
from unittest.mock import MagicMock

import pytest

from ly2mxml import state_resolver as _sr
from ly2mxml._types import _TransposeSpec


# ---------------------------------------------------------------------------
# resolve_clef
# ---------------------------------------------------------------------------


class TestResolveClef:
    def test_treble_clef(self):
        assert _sr.resolve_clef("treble") == ("G", 2, None)

    def test_bass_clef(self):
        assert _sr.resolve_clef("bass") == ("F", 4, None)

    def test_alto_clef(self):
        assert _sr.resolve_clef("alto") == ("C", 3, None)

    def test_tenor_clef(self):
        assert _sr.resolve_clef("tenor") == ("C", 4, None)

    def test_treble_8_clef(self):
        assert _sr.resolve_clef("treble_8") == ("G", 2, -1)

    def test_bass_8_clef(self):
        assert _sr.resolve_clef("bass_8") == ("F", 4, -1)

    def test_percussion_clef(self):
        sign, line, _ = _sr.resolve_clef("percussion")
        assert sign == "percussion"

    def test_case_insensitive(self):
        assert _sr.resolve_clef("Treble") == ("G", 2, None)

    def test_quoted_name(self):
        assert _sr.resolve_clef('"treble"') == ("G", 2, None)

    def test_unknown_clef_returns_none(self):
        assert _sr.resolve_clef("ukulele") is None

    def test_none_returns_none(self):
        assert _sr.resolve_clef(None) is None

    def test_empty_string_returns_none(self):
        assert _sr.resolve_clef("") is None


# ---------------------------------------------------------------------------
# key_fifths
# ---------------------------------------------------------------------------


class TestKeyFifths:
    def _make_pitch(self, note: int, alter: int | Fraction) -> object:
        """Create a minimal mock pitch object."""
        p = MagicMock()
        p.note = note
        p.alter = Fraction(alter)
        return p

    def test_c_major(self):
        pitch = self._make_pitch(0, 0)
        assert _sr.key_fifths(pitch, "major", ()) == 0

    def test_g_major_one_sharp(self):
        pitch = self._make_pitch(4, 0)  # G
        assert _sr.key_fifths(pitch, "major", ()) == 1

    def test_f_major_one_flat(self):
        pitch = self._make_pitch(3, 0)  # F
        assert _sr.key_fifths(pitch, "major", ()) == -1

    def test_a_minor(self):
        pitch = self._make_pitch(5, 0)  # A
        assert _sr.key_fifths(pitch, "minor", ()) == 0

    def test_e_minor_one_sharp(self):
        pitch = self._make_pitch(2, 0)  # E
        assert _sr.key_fifths(pitch, "minor", ()) == 1

    def test_unknown_combination_returns_zero(self):
        pitch = self._make_pitch(0, 5)  # invalid
        assert _sr.key_fifths(pitch, "major", ()) == 0


# ---------------------------------------------------------------------------
# to_pitch
# ---------------------------------------------------------------------------


class TestToPitch:
    def _make_pitch(self, note: int, alter: int | Fraction, octave: int) -> object:
        p = MagicMock()
        p.note = note
        p.alter = Fraction(alter)
        p.octave = octave
        return p

    def test_c4(self):
        # python-ly octave 0 → scientific octave 4 (octave + 4)
        raw = self._make_pitch(0, 0, 0)
        result = _sr.to_pitch(raw, ())
        assert result.step == "C"
        assert result.alter == 0
        assert result.octave == 4

    def test_g_sharp(self):
        # python-ly stores sharp as Fraction(1), not Fraction(1,2)
        raw = self._make_pitch(4, 1, 0)  # G# octave4
        result = _sr.to_pitch(raw, ())
        assert result.step == "G"
        assert result.alter == 1

    def test_b_flat(self):
        raw = self._make_pitch(6, -1, 0)  # Bb octave4
        result = _sr.to_pitch(raw, ())
        assert result.step == "B"
        assert result.alter == -1


# ---------------------------------------------------------------------------
# copy_pitch
# ---------------------------------------------------------------------------


class TestCopyPitch:
    def test_copies_pitch_with_copy_method(self):
        original = MagicMock()
        copy = MagicMock()
        original.copy.return_value = copy
        result = _sr.copy_pitch(original)
        assert result is copy
        original.copy.assert_called_once()

    def test_returns_original_when_no_copy_method(self):
        obj = object()
        result = _sr.copy_pitch(obj)
        assert result is obj


# ---------------------------------------------------------------------------
# grace_has_slash
# ---------------------------------------------------------------------------


class TestGraceHasSlash:
    def test_acciaccatura_has_slash(self):
        from ly.music import items

        node = MagicMock(spec=items.Grace)
        node.token = "\\acciaccatura"
        assert _sr.grace_has_slash(node) is True

    def test_appoggiatura_has_no_slash(self):
        from ly.music import items

        node = MagicMock(spec=items.Grace)
        node.token = "\\appoggiatura"
        assert _sr.grace_has_slash(node) is False

    def test_missing_token_has_no_slash(self):
        from ly.music import items

        node = MagicMock(spec=items.Grace)
        del node.token
        assert _sr.grace_has_slash(node) is False


# ---------------------------------------------------------------------------
# DEFAULT_CLEF constant
# ---------------------------------------------------------------------------


def test_default_clef_is_treble():
    assert _sr.DEFAULT_CLEF == ("G", 2, None)
