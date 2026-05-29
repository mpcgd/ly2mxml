from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_inspect_emits_json(repo_root: Path, sample_entrypoint: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "inspect", str(sample_entrypoint), "--json"],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    data = json.loads(result.stdout)

    assert data["entrypoint"].endswith("score.ly")
    assert any(path.endswith("music.ly") for path in data["included_files"])
    assert "global" in data["assignments"]


def test_cli_convert_accepts_include_cues(repo_root: Path, sample_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sample-include-cues.musicxml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ly2mxml",
            "convert",
            str(sample_entrypoint),
            "--include-cues",
            "-o",
            str(output_path),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stdout.strip().startswith("Wrote MusicXML")
    assert result.stderr.strip() == ""
    assert "<part-name>Flûte I</part-name>" in xml
    assert "<cue" not in xml