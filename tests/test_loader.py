from __future__ import annotations

from pathlib import Path

from ly2mxml.loader import ProjectLoader


def test_resolve_entrypoint_handles_existing_sample(sample_entrypoint: Path) -> None:
    loader = ProjectLoader()

    resolved = loader.resolve_entrypoint(sample_entrypoint)

    assert resolved == sample_entrypoint.resolve()
    assert resolved.name == "score.ly"


def test_read_text_reads_main_score(sample_entrypoint: Path) -> None:
    loader = ProjectLoader()

    source = loader.read_text(sample_entrypoint)

    assert "\\include \"music.ly\"" in source
    assert "\\score" in source
