"""Shared pytest fixtures for the converter's focused LilyPond samples.

Most fixtures map one `.ly` file to one syntax slice so new support claims can
be backed by compact, isolated regression inputs instead of only by the larger
acceptance sample.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ly2mxml.converter import LilypondConverter


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root used by file-based fixtures and CLI tests."""

    return Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_entrypoint(repo_root: Path) -> Path:
    """Return the acceptance sample project used for broader end-to-end checks."""

    return repo_root / "Test Sample" / "score.ly"


@pytest.fixture
def music21_module():
    """Import music21 lazily for importer-level validation tests."""

    return pytest.importorskip("music21")


@pytest.fixture
def sample_music21_scores(sample_entrypoint: Path, tmp_path: Path, music21_module):
    """Convert the sample project in both export modes for music21 validation."""

    separate_output = tmp_path / "sample-music21-separate.musicxml"
    combined_output = tmp_path / "sample-music21-combined.musicxml"

    LilypondConverter().convert_file(sample_entrypoint, separate_output)
    LilypondConverter(partcombine_mode="combined").convert_file(sample_entrypoint, combined_output)

    return (
        music21_module,
        music21_module.converter.parse(str(separate_output)),
        music21_module.converter.parse(str(combined_output)),
    )



# The remaining fixtures each point at one focused LilyPond sample so feature
# support claims can be tied back to a concrete regression input.

@pytest.fixture
def advanced_syntax_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "advanced_syntax.ly"


@pytest.fixture
def barlines_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "barlines.ly"


@pytest.fixture
def sfp_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "sfp.ly"


@pytest.fixture
def accent_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "accent.ly"


@pytest.fixture
def relative_tie_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "relative_ties.ly"


@pytest.fixture
def tied_trill_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "tied_trill.ly"


@pytest.fixture
def six_eight_multi_measure_rest_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "six_eight_multi_measure_rest.ly"


@pytest.fixture
def lyrics_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "lyrics.ly"


@pytest.fixture
def grace_subtypes_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "grace_subtypes.ly"


@pytest.fixture
def lyricsto_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "lyricsto.ly"


@pytest.fixture
def transpose_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "transpose.ly"


@pytest.fixture
def ottava_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "ottava.ly"


@pytest.fixture
def clef_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "clefs.ly"


@pytest.fixture
def cue_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "cues.ly"


@pytest.fixture
def transpose_cue_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "transpose_cues.ly"


@pytest.fixture
def scaled_cue_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "scaled_cues.ly"


@pytest.fixture
def relative_cue_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "relative_cues.ly"


@pytest.fixture
def tagged_cue_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "tagged_cues.ly"


@pytest.fixture
def tag_filter_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "tag_filter.ly"


@pytest.fixture
def multi_measure_rest_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "multi_measure_rest.ly"


@pytest.fixture
def uncompressed_rest_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "uncompressed_rest.ly"


@pytest.fixture
def missing_score_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "missing_score.ly"


@pytest.fixture
def lyric_surplus_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "lyric_surplus.ly"


@pytest.fixture
def extended_dynamics_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "extended_dynamics.ly"


@pytest.fixture
def staccatissimo_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "staccatissimo.ly"


@pytest.fixture
def ornaments_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "ornaments.ly"


@pytest.fixture
def fermata_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "fermata.ly"


@pytest.fixture
def technical_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "technical.ly"


@pytest.fixture
def explicit_articulations_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "explicit_articulations.ly"


@pytest.fixture
def extended_ornaments_technical_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "extended_ornaments_technical.ly"


@pytest.fixture
def tremolo_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "tremolo.ly"


@pytest.fixture
def inline_lyricsto_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "inline_lyricsto.ly"


@pytest.fixture
def keep_with_tag_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "keep_with_tag.ly"


@pytest.fixture
def multi_tag_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "multi_tag.ly"


@pytest.fixture
def voice_separator_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "voice_separator.ly"
