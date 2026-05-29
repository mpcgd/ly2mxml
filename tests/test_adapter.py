from __future__ import annotations

from pathlib import Path

from ly2mxml.frontend.python_ly_adapter import PythonLyAdapter
from ly2mxml.loader import ProjectLoader


class TrackingLoader(ProjectLoader):
    def __init__(self) -> None:
        super().__init__()
        self.read_calls: list[Path] = []

    def read_text(self, source_path: str | Path) -> str:
        resolved = self.resolve_entrypoint(source_path)
        self.read_calls.append(resolved)
        return super().read_text(resolved)


def test_inspect_collects_includes_assignments_and_features(sample_entrypoint: Path) -> None:
    analysis = PythonLyAdapter().inspect(sample_entrypoint)

    include_names = {path.name for path in analysis.included_files}

    assert analysis.document_count >= 3
    assert include_names == {"config.ly", "cues.ly", "music.ly"}
    assert "global" in analysis.assignments
    assert "fluteI" in analysis.assignments
    assert "scheme" in analysis.features
    assert "grace-notes" in analysis.features


def test_inspect_reports_known_sample_constructs(sample_entrypoint: Path) -> None:
    analysis = PythonLyAdapter().inspect(sample_entrypoint)

    assert analysis.user_command_counts["fluteI"] >= 1
    assert analysis.context_counts["Staff"] >= 1
    assert any(diagnostic.code == "unresolved-user-command" for diagnostic in analysis.diagnostics)


def test_load_document_tree_reads_entrypoint_through_loader(sample_entrypoint: Path) -> None:
    loader = TrackingLoader()
    adapter = PythonLyAdapter(loader=loader)

    document = adapter.load_document_tree(sample_entrypoint)

    assert loader.read_calls == [sample_entrypoint.resolve()]
    assert Path(document.document.filename).resolve() == sample_entrypoint.resolve()


def test_inspect_reads_includes_through_loader(sample_entrypoint: Path) -> None:
    loader = TrackingLoader()
    adapter = PythonLyAdapter(loader=loader)

    analysis = adapter.inspect(sample_entrypoint)

    loaded_names = {path.name for path in loader.read_calls}

    assert analysis.document_count >= 3
    assert {"score.ly", "config.ly", "cues.ly", "music.ly"}.issubset(loaded_names)
