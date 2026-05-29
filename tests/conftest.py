from __future__ import annotations

from pathlib import Path

import pytest

from ly2mxml.converter import LilypondConverter


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_entrypoint(repo_root: Path) -> Path:
    return repo_root / "Test Sample" / "score.ly"


@pytest.fixture
def music21_module():
    return pytest.importorskip("music21")


@pytest.fixture
def sample_music21_scores(sample_entrypoint: Path, tmp_path: Path, music21_module):
    separate_output = tmp_path / "sample-music21-separate.musicxml"
    combined_output = tmp_path / "sample-music21-combined.musicxml"

    LilypondConverter().convert_file(sample_entrypoint, separate_output)
    LilypondConverter(partcombine_mode="combined").convert_file(sample_entrypoint, combined_output)

    return (
        music21_module,
        music21_module.converter.parse(str(separate_output)),
        music21_module.converter.parse(str(combined_output)),
    )


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
