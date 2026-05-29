from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_entrypoint(repo_root: Path) -> Path:
    return repo_root / "Test Sample" / "score.ly"


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
def tag_filter_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "tag_filter.ly"


@pytest.fixture
def multi_measure_rest_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "multi_measure_rest.ly"


@pytest.fixture
def uncompressed_rest_entrypoint(repo_root: Path) -> Path:
    return repo_root / "tests" / "fixtures" / "uncompressed_rest.ly"
