from __future__ import annotations

from pathlib import Path

from ly2mxml.model.score import Score, ScoreMetadata
from ly2mxml.musicxml.writer import MusicXmlWriter


class CountingMusicXmlWriter(MusicXmlWriter):
    def __init__(self) -> None:
        self.build_tree_call_count = 0

    def build_tree(self, *args, **kwargs):
        self.build_tree_call_count += 1
        return super().build_tree(*args, **kwargs)


def test_write_builds_tree_once(tmp_path: Path) -> None:
    score = Score(metadata=ScoreMetadata(title="Title", composer="Composer"))
    writer = CountingMusicXmlWriter()
    output_path = tmp_path / "score.musicxml"

    writer.write(score, output_path)

    xml = output_path.read_text(encoding="utf-8")

    assert writer.build_tree_call_count == 1
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<movement-title>Title</movement-title>" in xml
    assert '<creator type="composer">Composer</creator>' in xml