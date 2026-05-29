from __future__ import annotations

from pathlib import Path

from ly2mxml.frontend.python_ly_adapter import PythonLyAdapter


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
