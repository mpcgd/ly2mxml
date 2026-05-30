from __future__ import annotations

from collections import Counter
from fractions import Fraction
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

from ly2mxml.converter import LilypondConverter
from ly2mxml.model.score import ClefChange
from ly2mxml.options import ExportOptions


def _music21_anchor_signature(note) -> tuple[int | None, str, str | tuple[str, ...]]:
    if note.isChord:
        pitch = tuple(pitch.nameWithOctave for pitch in note.pitches)
    elif note.isRest:
        pitch = "rest"
    else:
        pitch = note.pitch.nameWithOctave
    return note.measureNumber, str(note.offset), pitch


def _music21_text_expression_signature(score, music21) -> Counter[tuple[int | None, str, str]]:
    return Counter(
        (expression.measureNumber, str(expression.offset), expression.content)
        for expression in score.recurse().getElementsByClass(music21.expressions.TextExpression)
    )


def _music21_tempo_signature(score, music21) -> Counter[tuple[int | None, str, str | None, int | float | None]]:
    return Counter(
        (mark.measureNumber, str(mark.offset), getattr(mark, "text", None), getattr(mark, "number", None))
        for mark in score.recurse().getElementsByClass(music21.tempo.MetronomeMark)
    )


def _music21_wedge_type_signature(score, music21) -> Counter[str]:
    return Counter(type(wedge).__name__ for wedge in score.recurse().getElementsByClass(music21.dynamics.DynamicWedge))


def _music21_trill_extension_signature(score, music21) -> Counter[tuple[tuple, tuple]]:
    return Counter(
        (_music21_anchor_signature(extension.getFirst()), _music21_anchor_signature(extension.getLast()))
        for extension in score.recurse().getElementsByClass(music21.expressions.TrillExtension)
    )


def test_preflight_accepts_sample_project(sample_entrypoint: Path) -> None:
    preflight = LilypondConverter().preflight(sample_entrypoint)

    assert not preflight.has_errors
    assert "part-combine" in preflight.supported_features


def test_converter_defaults_to_ignoring_cues(sample_entrypoint: Path) -> None:
    converter = LilypondConverter()

    assert converter.export_options.cue_mode == "ignore"

    preflight = converter.preflight(sample_entrypoint)

    assert "cue-filtering" in preflight.supported_features
    assert "cue-quotes" in preflight.supported_features


def test_build_score_extracts_parts_and_voices(sample_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(sample_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)
    assert score.metadata.title == "Hymne à l'agriculture"
    assert score.metadata.composer == "Jean-Xavier Lefèvre"
    assert len(score.parts) >= 20
    assert score.parts[0].name == "Flûte I"
    assert score.parts[1].name == "Flûte II"
    assert score.parts[0].combined_name == "Flûtes"
    assert score.parts[0].combine_group == score.parts[1].combine_group
    assert len(score.parts[0].voices) == 1
    assert score.parts[0].time_signature == (6, 8)

    first_event = next(event for event in score.parts[0].voices[0].measures[0].events if event.is_note)
    assert first_event.pitches[0].step == "A"
    assert first_event.pitches[0].octave >= 5


def test_cli_convert_writes_musicxml(repo_root: Path, sample_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sample.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(sample_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stdout.strip().startswith("Wrote MusicXML")
    assert result.stderr.strip() == ""
    assert "<score-partwise" in xml
    assert "<movement-title>Hymne à l'agriculture</movement-title>" in xml
    assert "<part-name>Flûte I</part-name>" in xml
    assert "<part-name>Flûte II</part-name>" in xml
    assert "<multiple-rest>" in xml
    assert "<step>A</step>" in xml
    assert "<wedge type=\"crescendo\"" in xml


def test_cli_convert_pads_empty_sample_parts(repo_root: Path, sample_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sample-empty-parts.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(sample_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stderr.strip() == ""

    root = ET.parse(output_path).getroot()
    part_names = {score_part.attrib["id"]: score_part.findtext("part-name") for score_part in root.find("part-list")}

    for expected_name in {"Hautbois I", "Hautbois II"}:
        part = next(part for part in root.findall("part") if part_names.get(part.attrib["id"]) == expected_name)
        measures = part.findall("measure")
        divisions = int(measures[0].findtext("./attributes/divisions"))

        assert len(measures) == 76
        assert measures[0].findtext("./attributes/measure-style/multiple-rest") == "75"
        assert measures[-1].findtext("./note/duration") == str(3 * divisions // 2)
        assert measures[-1].find("./note/rest") is not None
        assert measures[-1].findtext("./barline/bar-style") == "light-heavy"


def test_cli_convert_writes_opening_tempo_once(repo_root: Path, sample_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sample-tempo.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(sample_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stderr.strip() == ""

    root = ET.parse(output_path).getroot()
    tempo_locations: list[tuple[str | None, str | None]] = []
    part_names = {score_part.attrib["id"]: score_part.findtext("part-name") for score_part in root.find("part-list")}
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            for words in measure.findall("./direction/direction-type/words"):
                if words.text == "Maestoso":
                    tempo_locations.append((part_names.get(part.attrib["id"]), measure.attrib.get("number")))

    assert tempo_locations == [("Flûte I", "1")]


def test_cli_convert_does_not_emit_orphan_wedge_stops(repo_root: Path, sample_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sample-no-orphan-wedges.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(sample_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stderr.strip() == ""

    root = ET.parse(output_path).getroot()
    part_names = {score_part.attrib["id"]: score_part.findtext("part-name") for score_part in root.find("part-list")}
    orphan_stops: list[tuple[str | None, str | None]] = []
    open_wedges: list[tuple[str | None, str | None]] = []

    for part in root.findall("part"):
        active_wedge = False
        active_measure = None
        for measure in part.findall("measure"):
            for direction in measure.findall("direction"):
                wedge = direction.find("./direction-type/wedge")
                if wedge is None:
                    continue
                wedge_type = wedge.attrib.get("type")
                if wedge_type in {"crescendo", "diminuendo"}:
                    active_wedge = True
                    active_measure = measure.attrib.get("number")
                elif wedge_type == "stop":
                    if not active_wedge:
                        orphan_stops.append((part_names.get(part.attrib["id"]), measure.attrib.get("number")))
                    active_wedge = False
                    active_measure = None

        if active_wedge:
            open_wedges.append((part_names.get(part.attrib["id"]), active_measure))

    assert orphan_stops == []
    assert open_wedges == []


def test_convert_file_can_merge_partcombine_groups(sample_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sample-combined.musicxml"

    result = LilypondConverter(partcombine_mode="combined").convert_file(sample_entrypoint, output_path)

    assert result.output_path == output_path
    assert result.score is not None

    xml = output_path.read_text(encoding="utf-8")

    assert "<part-name>Flûtes</part-name>" in xml
    assert "<part-name>Flûte I</part-name>" not in xml
    assert xml.count("<part id=") < len(result.score.parts)


def test_convert_file_accepts_export_options(sample_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sample-combined-options.musicxml"

    result = LilypondConverter(export_options=ExportOptions(partcombine_mode="combined")).convert_file(
        sample_entrypoint,
        output_path,
    )

    assert result.output_path == output_path

    xml = output_path.read_text(encoding="utf-8")

    assert "<part-name>Flûtes</part-name>" in xml
    assert "<part-name>Flûte I</part-name>" not in xml


def test_preflight_accepts_supported_repeats_and_scalers(advanced_syntax_entrypoint: Path) -> None:
    preflight = LilypondConverter().preflight(advanced_syntax_entrypoint)

    assert not preflight.has_errors
    assert "scaled-durations" in preflight.supported_features
    assert "repeat:unfold" in preflight.supported_features
    assert "repeat:volta" in preflight.supported_features


def test_preflight_accepts_barlines(barlines_entrypoint: Path) -> None:
    preflight = LilypondConverter().preflight(barlines_entrypoint)

    assert not preflight.has_errors
    assert "barlines" in preflight.supported_features


def test_preflight_accepts_transpose(transpose_entrypoint: Path) -> None:
    preflight = LilypondConverter().preflight(transpose_entrypoint)

    assert not preflight.has_errors
    assert "transpose" in preflight.supported_features


def test_build_score_preserves_mid_staff_clef_changes(clef_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(clef_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    part = score.parts[0]
    voice = part.voices[0]

    assert (part.clef_sign, part.clef_line) == ("G", 2)
    assert voice.measures[0].clef_changes == [
        ClefChange(offset=Fraction(1, 2), sign="F", line=4),
    ]
    assert voice.measures[1].clef_changes == [
        ClefChange(offset=Fraction(0, 1), sign="C", line=4),
        ClefChange(offset=Fraction(1, 2), sign="percussion", line=2),
    ]
    assert voice.measures[2].clef_changes == [
        ClefChange(offset=Fraction(0, 1), sign="G", line=2, octave_change=-1),
    ]


def test_build_score_flattens_repeats_and_captures_tuplets(advanced_syntax_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(advanced_syntax_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)
    part = score.parts[0]
    voice = part.voices[0]

    note_events = [event for measure in voice.measures for event in measure.events if event.is_note]
    step_sequence = [event.pitches[0].step for event in note_events]

    assert step_sequence[-8:] == ["B", "C", "D", "E", "B", "C", "F", "G"]
    assert any(event.time_modification == (3, 2) and event.tuplet_start for event in note_events)
    assert any(event.time_modification == (3, 2) and event.tuplet_stop for event in note_events)
    assert any(direction.kind == "wedge" and direction.value == "crescendo" for event in note_events for direction in event.directions)
    assert any(direction.kind == "wedge" and direction.value == "stop" for event in note_events for direction in event.directions)


def test_cli_convert_writes_tuplets_and_repeats(repo_root: Path, advanced_syntax_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "advanced.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(advanced_syntax_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert xml.count("<time-modification>") >= 6
    assert "<tuplet type=\"start\" number=\"1\"" in xml
    assert "<tuplet type=\"stop\" number=\"1\"" in xml
    assert "<wedge type=\"crescendo\"" in xml
    assert "<wedge type=\"stop\"" in xml


def test_cli_convert_writes_explicit_barlines(repo_root: Path, barlines_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "barlines.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(barlines_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert '<barline location="right">' in xml
    assert '<bar-style>light-light</bar-style>' in xml
    assert '<bar-style>light-heavy</bar-style>' in xml


def test_cli_convert_writes_command_form_sfp(repo_root: Path, sfp_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sfp.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(sfp_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<sfp />" in xml


def test_cli_convert_writes_arrow_accent(repo_root: Path, accent_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "accent.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(accent_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<accent />" in xml

def test_cli_convert_writes_relative_tie_stops(repo_root: Path, relative_tie_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "relative_ties.musicxml"

    completed = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(relative_tie_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    xml = output_path.read_text(encoding="utf-8")

    assert xml.count('<tie type="start" />') == 2
    assert xml.count('<tie type="stop" />') == 2


def test_cli_convert_writes_trill_wavy_line(repo_root: Path, tied_trill_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "tied_trill.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(tied_trill_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert xml.count('<trill-mark />') == 1
    assert xml.count('<wavy-line type="start" />') == 1
    assert xml.count('<wavy-line type="continue" />') == 1
    assert xml.count('<wavy-line type="stop" />') == 1


def test_cli_convert_can_merge_partcombine_groups(repo_root: Path, sample_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "sample-combined-cli.musicxml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ly2mxml",
            "convert",
            str(sample_entrypoint),
            "--partcombine-mode",
            "combined",
            "-o",
            str(output_path),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<part-name>Flûtes</part-name>" in xml
    assert "<part-name>Flûte I</part-name>" not in xml


def test_cli_convert_combined_mode_scopes_wedges_by_voice(
    repo_root: Path,
    sample_entrypoint: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "sample-combined-wedges.musicxml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ly2mxml",
            "convert",
            str(sample_entrypoint),
            "--partcombine-mode",
            "combined",
            "-o",
            str(output_path),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stderr.strip() == ""

    root = ET.parse(output_path).getroot()
    orphan_stops: list[tuple[str, str | None, str]] = []
    open_wedges: list[tuple[str, str, str | None]] = []
    saw_secondary_voice = False

    for part in root.findall("part"):
        active_wedges: dict[str, tuple[str, str | None]] = {}
        for measure in part.findall("measure"):
            for direction in measure.findall("direction"):
                wedge = direction.find("./direction-type/wedge")
                if wedge is None:
                    continue
                voice = direction.findtext("voice") or "1"
                if voice != "1":
                    saw_secondary_voice = True
                wedge_type = wedge.attrib.get("type")
                if wedge_type in {"crescendo", "diminuendo"}:
                    active_wedges[voice] = (wedge_type, measure.attrib.get("number"))
                elif wedge_type == "stop":
                    if voice not in active_wedges:
                        orphan_stops.append((part.attrib["id"], measure.attrib.get("number"), voice))
                    active_wedges.pop(voice, None)
        for voice, (_, measure_number) in sorted(active_wedges.items()):
            open_wedges.append((part.attrib["id"], voice, measure_number))

    assert saw_secondary_voice
    assert orphan_stops == []
    assert open_wedges == []


def test_cli_convert_combined_mode_preserves_empty_part_multirests(
    repo_root: Path,
    sample_entrypoint: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "sample-combined-empty-parts.musicxml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ly2mxml",
            "convert",
            str(sample_entrypoint),
            "--partcombine-mode",
            "combined",
            "-o",
            str(output_path),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stderr.strip() == ""

    root = ET.parse(output_path).getroot()
    part_names = {score_part.attrib["id"]: score_part.findtext("part-name") for score_part in root.find("part-list")}
    part = next(part for part in root.findall("part") if part_names.get(part.attrib["id"]) == "Hautbois (ad lib.)")
    measures = part.findall("measure")
    divisions = int(measures[0].findtext("./attributes/divisions"))
    last = measures[-1]
    last_notes = last.findall("./note")
    first_notes = measures[0].findall("./note")

    assert len(measures) == 76
    assert measures[0].findtext("./attributes/measure-style/multiple-rest") == "75"
    assert measures[0].find("./backup") is None
    assert [note.findtext("voice") for note in first_notes] == ["1"]
    assert all(note.find("rest") is not None for note in first_notes)
    assert last.findtext("./backup/duration") == str(3 * divisions // 2)
    assert last.findtext("./barline/bar-style") == "light-heavy"
    assert [note.findtext("voice") for note in last_notes] == ["1", "2"]
    assert all(note.find("rest") is not None for note in last_notes)
    assert all(note.findtext("duration") == str(3 * divisions // 2) for note in last_notes)


def test_cli_convert_combined_mode_uses_single_rest_for_multimeasure_rests(
    repo_root: Path,
    sample_entrypoint: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "sample-combined-multirests.musicxml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ly2mxml",
            "convert",
            str(sample_entrypoint),
            "--partcombine-mode",
            "combined",
            "-o",
            str(output_path),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stderr.strip() == ""

    root = ET.parse(output_path).getroot()
    multiple_rest_measures = [
        measure
        for part in root.findall("part")
        for measure in part.findall("measure")
        if measure.find("./attributes/measure-style/multiple-rest") is not None
    ]

    assert multiple_rest_measures
    assert all(len(measure.findall("./note")) == 1 for measure in multiple_rest_measures)
    assert all(measure.find("./backup") is None for measure in multiple_rest_measures)


def test_cli_convert_combined_mode_scopes_slurs_by_voice(
    repo_root: Path,
    sample_entrypoint: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "sample-combined-slurs.musicxml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ly2mxml",
            "convert",
            str(sample_entrypoint),
            "--partcombine-mode",
            "combined",
            "-o",
            str(output_path),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stderr.strip() == ""

    root = ET.parse(output_path).getroot()
    saw_voice_two_slur = False

    for note in root.findall('.//note'):
        voice = note.findtext('voice') or '1'
        slurs = note.findall('./notations/slur')
        if not slurs:
            continue
        if voice == '2':
            saw_voice_two_slur = True
        assert all(slur.attrib.get('number') == voice for slur in slurs)

    assert saw_voice_two_slur


def test_music21_import_preserves_sample_text_and_tempo_signatures(sample_music21_scores) -> None:
    music21, separate_score, combined_score = sample_music21_scores

    separate_text = _music21_text_expression_signature(separate_score, music21)
    combined_text = _music21_text_expression_signature(combined_score, music21)

    assert separate_text == combined_text
    assert separate_text[(1, "0.0", "Maestoso")] == 1
    assert _music21_tempo_signature(separate_score, music21) == _music21_tempo_signature(combined_score, music21)


def test_music21_import_preserves_sample_wedge_types(sample_music21_scores) -> None:
    music21, separate_score, combined_score = sample_music21_scores

    separate_wedges = _music21_wedge_type_signature(separate_score, music21)
    combined_wedges = _music21_wedge_type_signature(combined_score, music21)

    assert separate_wedges == combined_wedges
    assert sum(separate_wedges.values()) == 35


def test_music21_import_preserves_sample_trill_extensions(sample_music21_scores) -> None:
    music21, separate_score, combined_score = sample_music21_scores

    separate_trills = _music21_trill_extension_signature(separate_score, music21)
    combined_trills = _music21_trill_extension_signature(combined_score, music21)

    assert separate_trills == combined_trills
    assert sum(separate_trills.values()) == 2


def test_build_score_attaches_addlyrics(lyrics_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(lyrics_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [event for measure in score.parts[0].voices[0].measures for event in measure.events if event.is_note]

    assert [event.lyrics[0].text for event in note_events if event.lyrics] == ["Hel", "lo", "world", "song"]
    assert note_events[0].lyrics[0].syllabic == "begin"
    assert note_events[1].lyrics[0].syllabic == "end"


def test_build_score_distinguishes_grace_subtypes(grace_subtypes_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(grace_subtypes_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [event for measure in score.parts[0].voices[0].measures for event in measure.events if event.is_note]

    assert note_events[0].is_grace is True
    assert note_events[0].grace_slash is True
    assert note_events[2].is_grace is True
    assert note_events[2].grace_slash is False


def test_build_score_captures_explicit_barlines(barlines_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(barlines_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    measures = score.parts[0].voices[0].measures

    assert measures[0].right_barline == "light-light"
    assert measures[1].right_barline == "light-heavy"


def test_build_score_emits_command_form_sfp_dynamic(sfp_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(sfp_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [event for measure in score.parts[0].voices[0].measures for event in measure.events if event.is_note]

    assert [direction.value for direction in note_events[0].directions if direction.kind == "dynamic"] == ["sfp"]


def test_build_score_emits_arrow_accent_articulation(accent_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(accent_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [event for measure in score.parts[0].voices[0].measures for event in measure.events if event.is_note]

    assert note_events[0].articulations == ["accent"]

def test_build_score_resolves_relative_tied_notes(relative_tie_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(relative_tie_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [event for measure in score.parts[0].voices[0].measures for event in measure.events if event.is_note]

    assert [event.pitches[0].octave for event in note_events] == [3, 3, 3]
    assert [(event.tie_start, event.tie_stop) for event in note_events] == [(True, False), (True, True), (False, True)]


def test_build_score_keeps_single_trill_mark_on_tied_chain(tied_trill_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(tied_trill_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [event for measure in score.parts[0].voices[0].measures for event in measure.events if event.is_note]

    assert [event.ornaments for event in note_events] == [["trill-mark"], [], []]
    assert [(event.tie_start, event.tie_stop) for event in note_events] == [(True, False), (True, True), (False, True)]


def test_build_score_attaches_lyricsto_multiple_verses(lyricsto_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(lyricsto_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [event for measure in score.parts[0].voices[0].measures for event in measure.events if event.is_note]

    assert [[lyric.text for lyric in event.lyrics] for event in note_events] == [
        ["Hel", "Bye"],
        ["lo", "night"],
        ["world", "moon"],
        ["song", "light"],
    ]
    assert [lyric.number for lyric in note_events[0].lyrics] == [1, 2]
    assert note_events[0].lyrics[0].syllabic == "begin"
    assert note_events[1].lyrics[0].syllabic == "end"


def test_build_score_applies_transpose_to_notes_and_key(transpose_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(transpose_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    part = score.parts[0]
    note_events = [event for measure in part.voices[0].measures for event in measure.events if event.is_note]

    assert part.key_fifths == 2
    assert [(event.pitches[0].step, event.pitches[0].alter) for event in note_events] == [
        ("D", 0),
        ("E", 0),
        ("F", 1),
        ("G", 0),
    ]


def test_build_score_emits_ottava_start_and_stop_directions(ottava_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(ottava_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [event for measure in score.parts[0].voices[0].measures for event in measure.events if event.is_note]

    assert [direction.value for direction in note_events[0].directions if direction.kind == "octave-shift"] == ["above:down:8"]
    assert not any(direction.kind == "octave-shift" for direction in note_events[1].directions)
    assert [direction.value for direction in note_events[2].directions if direction.kind == "octave-shift"] == ["above:stop:8"]
    assert not any(direction.kind == "octave-shift" for direction in note_events[3].directions)


def test_build_score_preserves_cue_duration_when_cues_are_ignored(cue_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(cue_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    voice = score.parts[0].voices[0]
    first_measure = voice.measures[0]
    second_measure = voice.measures[1]

    assert first_measure.duration == Fraction(1, 1)
    assert second_measure.duration == Fraction(1, 1)
    assert len(first_measure.events) == 1
    assert first_measure.events[0].is_rest is True
    assert first_measure.events[0].is_cue is False
    assert second_measure.events[0].is_rest is True


def test_build_score_preserves_transposed_cue_duration_when_cues_are_ignored(transpose_cue_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(transpose_cue_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    voice = score.parts[0].voices[0]
    first_measure = voice.measures[0]
    second_measure = voice.measures[1]

    assert first_measure.duration == Fraction(1, 1)
    assert len(first_measure.events) == 1
    assert first_measure.events[0].is_rest is True
    assert first_measure.events[0].is_cue is False
    assert second_measure.duration == Fraction(1, 1)
    assert len(second_measure.events) == 1
    assert second_measure.events[0].is_note is True
    assert second_measure.events[0].is_cue is False


def test_build_score_preserves_scaled_cue_duration_when_cues_are_ignored(scaled_cue_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(scaled_cue_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    voice = score.parts[0].voices[0]
    first_measure = voice.measures[0]
    second_measure = voice.measures[1]

    assert first_measure.duration == Fraction(1, 1)
    assert len(first_measure.events) == 1
    assert first_measure.events[0].is_rest is True
    assert first_measure.events[0].is_cue is False
    assert second_measure.duration == Fraction(1, 1)
    assert len(second_measure.events) == 1
    assert second_measure.events[0].is_note is True
    assert second_measure.events[0].is_cue is False


def test_build_score_preserves_relative_cue_duration_when_cues_are_ignored(relative_cue_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(relative_cue_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    voice = score.parts[0].voices[0]
    first_measure = voice.measures[0]
    second_measure = voice.measures[1]

    assert first_measure.duration == Fraction(1, 1)
    assert len(first_measure.events) == 1
    assert first_measure.events[0].is_rest is True
    assert first_measure.events[0].is_cue is False
    assert second_measure.duration == Fraction(1, 1)
    assert len(second_measure.events) == 1
    assert second_measure.events[0].is_note is True
    assert second_measure.events[0].is_cue is False


def test_build_score_preserves_tagged_cue_duration_when_cues_are_ignored(tagged_cue_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(tagged_cue_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    voice = score.parts[0].voices[0]
    first_measure = voice.measures[0]
    second_measure = voice.measures[1]

    assert first_measure.duration == Fraction(1, 1)
    assert len(first_measure.events) == 1
    assert first_measure.events[0].is_rest is True
    assert first_measure.events[0].is_cue is False
    assert second_measure.duration == Fraction(1, 1)
    assert len(second_measure.events) == 1
    assert second_measure.events[0].is_note is True
    assert second_measure.events[0].is_cue is False


def test_build_score_includes_cue_notes_when_requested(cue_entrypoint: Path) -> None:
    score = LilypondConverter(export_options=ExportOptions(cue_mode="include")).build_score(cue_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    voice = score.parts[0].voices[0]
    cue_events = [event for event in voice.measures[0].events if event.is_note and event.is_cue]

    assert [event.pitches[0].step for event in cue_events] == ["C", "D", "E", "F"]
    assert cue_events[0].articulations == ["staccato"]
    assert voice.measures[1].events[0].is_rest is True
    assert not any(event.is_cue for event in voice.measures[1].events)


def test_build_score_applies_remove_with_tag_filter(tag_filter_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(tag_filter_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    voice = score.parts[0].voices[0]
    note_events = [event for measure in voice.measures for event in measure.events if event.is_note]

    assert [event.pitches[0].step for event in note_events] == ["D", "E"]


def test_build_score_marks_compressed_empty_measures(multi_measure_rest_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(multi_measure_rest_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)
    assert score.parts[0].voices[0].compress_empty_measures is True


def test_build_score_treats_uppercase_rest_repeat_as_measure_count_in_six_eight(
    six_eight_multi_measure_rest_entrypoint: Path,
) -> None:
    score = LilypondConverter().build_score(six_eight_multi_measure_rest_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    voice = score.parts[0].voices[0]

    assert len(voice.measures) == 11
    assert all(len(measure.events) == 1 and measure.events[0].is_rest for measure in voice.measures[:10])


def test_cli_convert_writes_multiple_rest_measure_style(
    repo_root: Path,
    multi_measure_rest_entrypoint: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "multi-rest.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(multi_measure_rest_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<multiple-rest>4</multiple-rest>" in xml


def test_cli_convert_writes_six_eight_multiple_rest_measure_style(
    repo_root: Path,
    six_eight_multi_measure_rest_entrypoint: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "six-eight-multi-rest.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(six_eight_multi_measure_rest_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<multiple-rest>10</multiple-rest>" in xml


def test_cli_convert_writes_cue_notes_when_enabled(repo_root: Path, cue_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "cues.musicxml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ly2mxml",
            "convert",
            str(cue_entrypoint),
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

    assert result.stderr.strip() == ""
    assert "<cue" in xml
    assert xml.count("<cue") >= 4
    assert "<staccato" in xml


def test_cli_convert_respects_remove_with_tag_filter(repo_root: Path, tag_filter_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "tag-filter.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(tag_filter_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<step>D</step>" in xml
    assert "<step>E</step>" in xml
    assert "<step>C</step>" not in xml


def test_cli_convert_does_not_write_multiple_rest_without_command(
    repo_root: Path,
    uncompressed_rest_entrypoint: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "uncompressed-rest.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(uncompressed_rest_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<multiple-rest>" not in xml


def test_cli_convert_writes_lyrics(repo_root: Path, lyrics_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "lyrics.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(lyrics_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<lyric>" in xml
    assert "<syllabic>begin</syllabic>" in xml
    assert "<text>Hel</text>" in xml
    assert "<text>world</text>" in xml


def test_cli_convert_writes_slashed_acciaccatura(repo_root: Path, grace_subtypes_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "grace-subtypes.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(grace_subtypes_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert '<grace slash="yes"' in xml
    assert xml.count("<grace") == 2


def test_cli_convert_writes_lyricsto_multiple_verses(repo_root: Path, lyricsto_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "lyricsto.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(lyricsto_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert '<lyric number="1">' in xml
    assert '<lyric number="2">' in xml
    assert "<text>Hel</text>" in xml
    assert "<text>Bye</text>" in xml


def test_cli_convert_writes_transposed_key_and_notes(repo_root: Path, transpose_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "transpose.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(transpose_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<fifths>2</fifths>" in xml
    assert "<step>D</step>" in xml
    assert "<step>F</step>" in xml
    assert "<alter>1</alter>" in xml


def test_cli_convert_writes_mid_staff_clef_changes(repo_root: Path, clef_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "clefs.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(clef_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    root = ET.parse(output_path).getroot()

    assert result.stderr.strip() == ""

    part = root.find("part")
    assert part is not None

    first_measure = part.findall("measure")[0]
    first_measure_clefs = first_measure.findall("./attributes/clef")
    assert len(first_measure_clefs) == 2
    assert first_measure_clefs[0].findtext("sign") == "G"
    assert first_measure_clefs[0].findtext("line") == "2"
    assert first_measure_clefs[1].findtext("sign") == "F"
    assert first_measure_clefs[1].findtext("line") == "4"

    second_measure = part.findall("measure")[1]
    second_measure_clefs = second_measure.findall("./attributes/clef")
    assert len(second_measure_clefs) == 2
    assert second_measure_clefs[0].findtext("sign") == "C"
    assert second_measure_clefs[0].findtext("line") == "4"
    assert second_measure_clefs[1].findtext("sign") == "percussion"
    assert second_measure_clefs[1].findtext("line") == "2"

    third_measure = part.findall("measure")[2]
    third_measure_clefs = third_measure.findall("./attributes/clef")
    assert len(third_measure_clefs) == 1
    assert third_measure_clefs[0].findtext("sign") == "G"
    assert third_measure_clefs[0].findtext("line") == "2"
    assert third_measure_clefs[0].findtext("clef-octave-change") == "-1"


def test_cli_convert_writes_ottava_octave_shift(repo_root: Path, ottava_entrypoint: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "ottava.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(ottava_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert '<direction placement="above">' in xml
    assert '<octave-shift type="down" size="8"' in xml
    assert '<octave-shift type="stop" size="8"' in xml


def test_build_score_emits_missing_score_diagnostic(missing_score_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(missing_score_entrypoint)

    codes = [d.code for d in score.diagnostics]
    assert "missing-score" in codes
    assert any(d.severity == "error" for d in score.diagnostics if d.code == "missing-score")
    assert score.parts == []


def test_build_score_warns_on_lyric_surplus(lyric_surplus_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(lyric_surplus_entrypoint)

    warning_codes = [d.code for d in score.diagnostics if d.severity == "warning"]
    assert "lyric-surplus" in warning_codes


def test_converter_raises_on_conflicting_partcombine_mode() -> None:
    import pytest as _pytest
    from ly2mxml.options import ExportOptions

    with _pytest.raises(ValueError, match="Conflicting partcombine_mode"):
        LilypondConverter(
            partcombine_mode="combined",
            export_options=ExportOptions(partcombine_mode="separate"),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Extended dynamic marks
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_extended_dynamics(extended_dynamics_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(extended_dynamics_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]
    dynamic_values = [
        direction.value
        for event in note_events
        for direction in event.directions
        if direction.kind == "dynamic"
    ]

    assert "ppp" in dynamic_values
    assert "pppp" in dynamic_values
    assert "ffff" in dynamic_values
    assert "fp" in dynamic_values
    assert "fz" in dynamic_values
    assert "rfz" in dynamic_values
    assert "rf" in dynamic_values
    assert "sfz" in dynamic_values
    assert "sff" in dynamic_values
    assert "sffz" in dynamic_values
    assert "sfpp" in dynamic_values


def test_cli_convert_writes_extended_dynamics(
    repo_root: Path, extended_dynamics_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "extended_dynamics.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(extended_dynamics_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<ppp />" in xml
    assert "<pppp />" in xml
    assert "<ffff />" in xml
    assert "<fp />" in xml
    assert "<fz />" in xml
    assert "<rfz />" in xml
    assert "<rf />" in xml
    assert "<sfz />" in xml
    assert "<sff />" in xml
    assert "<sffz />" in xml
    assert "<sfpp />" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Extended articulations: staccatissimo and detached-legato
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_staccatissimo_and_detached_legato(staccatissimo_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(staccatissimo_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    assert note_events[0].articulations == ["staccatissimo"]
    assert note_events[1].articulations == ["detached-legato"]


def test_cli_convert_writes_staccatissimo_and_detached_legato(
    repo_root: Path, staccatissimo_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "staccatissimo.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(staccatissimo_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<staccatissimo />" in xml
    assert "<detached-legato />" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Extended ornaments: mordent, prall, turn, reverseturn
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_ornaments(ornaments_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(ornaments_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    assert note_events[0].ornaments == ["mordent"]
    assert note_events[1].ornaments == ["inverted-mordent"]
    assert note_events[2].ornaments == ["turn"]
    assert note_events[3].ornaments == ["inverted-turn"]


def test_cli_convert_writes_ornaments(
    repo_root: Path, ornaments_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "ornaments.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(ornaments_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<mordent />" in xml
    assert "<inverted-mordent />" in xml
    assert "<turn />" in xml
    assert "<inverted-turn />" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Fermata notation
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_fermata_variants(fermata_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(fermata_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    assert note_events[0].fermatas == [""]
    assert note_events[1].fermatas == ["square"]
    assert note_events[3].fermatas == ["angled"]
    assert note_events[5].fermatas == ["square"]


def test_cli_convert_writes_fermata(
    repo_root: Path, fermata_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "fermata.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(fermata_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert '<fermata type="upright"' in xml
    assert ">angled<" in xml
    assert ">square<" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Technical notations
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_technical_notations(technical_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(technical_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    assert note_events[0].technical == ["up-bow"]
    assert note_events[1].technical == ["down-bow"]
    assert note_events[2].technical == ["stopped"]
    assert note_events[3].technical == ["open-string"]


def test_cli_convert_writes_technical_notations(
    repo_root: Path, technical_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "technical.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(technical_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<technical>" in xml
    assert "<up-bow />" in xml
    assert "<down-bow />" in xml
    assert "<stopped />" in xml
    assert "<open-string />" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Explicit command-form articulations
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_explicit_articulation_commands(explicit_articulations_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(explicit_articulations_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    assert note_events[0].articulations == ["staccato"]
    assert note_events[1].articulations == ["tenuto"]
    assert note_events[2].articulations == ["strong-accent"]
    assert note_events[3].articulations == ["accent"]
    assert note_events[4].articulations == ["soft-accent"]
    assert note_events[5].articulations == ["detached-legato"]
    assert note_events[6].articulations == ["staccatissimo"]


def test_cli_convert_writes_explicit_articulation_commands(
    repo_root: Path, explicit_articulations_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "explicit_articulations.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(explicit_articulations_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<staccato />" in xml
    assert "<tenuto />" in xml
    assert "<strong-accent />" in xml
    assert "<accent />" in xml
    assert "<soft-accent />" in xml
    assert "<detached-legato />" in xml
    assert "<staccatissimo />" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Extended ornaments and technical marks
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_extended_ornaments_and_technical(
    extended_ornaments_technical_entrypoint: Path,
) -> None:
    score = LilypondConverter().build_score(extended_ornaments_technical_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    assert note_events[0].ornaments == ["mordent"]        # \prallmordent
    assert note_events[1].ornaments == ["inverted-mordent"]  # \prallprall
    assert note_events[2].ornaments == ["mordent"]        # \downmordent
    assert note_events[3].ornaments == ["inverted-mordent"]  # \upmordent
    assert note_events[4].technical == ["heel"]           # \lheel
    assert note_events[5].technical == ["heel"]           # \rheel
    assert note_events[6].technical == ["toe"]            # \ltoe
    assert note_events[7].technical == ["toe"]            # \rtoe


def test_cli_convert_writes_extended_ornaments_and_technical(
    repo_root: Path, extended_ornaments_technical_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "extended_ornaments_technical.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(extended_ornaments_technical_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<mordent />" in xml
    assert "<inverted-mordent />" in xml
    assert "<heel />" in xml
    assert "<toe />" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Tremolo repeats
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_tremolo(tremolo_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(tremolo_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    # Single-note tremolo: \repeat tremolo 4 { c16 } → c quarter with 2 slashes
    assert note_events[0].tremolo_type == "single"
    assert note_events[0].tremolo_slashes == 2

    # Two-note tremolo: \repeat tremolo 4 { d16 e16 } → d quarter start, e quarter stop
    assert note_events[1].tremolo_type == "start"
    assert note_events[1].tremolo_slashes == 2
    assert note_events[2].tremolo_type == "stop"
    assert note_events[2].tremolo_slashes == 2


def test_cli_convert_writes_tremolo(
    repo_root: Path, tremolo_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "tremolo.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(tremolo_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert '<tremolo type="single">2</tremolo>' in xml
    assert '<tremolo type="start">2</tremolo>' in xml
    assert '<tremolo type="stop">2</tremolo>' in xml


# ──────────────────────────────────────────────────────────────────────────────
# Inline \lyricsto form: \new Lyrics { \lyricsto "voice" { words } }
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_applies_inline_lyricsto(inline_lyricsto_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(inline_lyricsto_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    # "Hel -- lo world" → Hel(begin), lo(end), world(single)
    assert note_events[0].lyrics and note_events[0].lyrics[0].syllabic == "begin"
    assert note_events[1].lyrics and note_events[1].lyrics[0].syllabic == "end"
    assert note_events[2].lyrics and note_events[2].lyrics[0].text == "world"
    assert note_events[2].lyrics[0].syllabic == "single"


def test_cli_convert_writes_inline_lyricsto(
    repo_root: Path, inline_lyricsto_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "inline_lyricsto.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(inline_lyricsto_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<lyric" in xml
    assert "<text>world</text>" in xml


# ──────────────────────────────────────────────────────────────────────────────
# \keepWithTag filtering
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_applies_keepwithtag(keep_with_tag_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(keep_with_tag_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    # \keepWithTag #'solo keeps: \tag #'solo { c'4 }, untagged e'4, \tag #'solo { f'4 }
    # \tag #'tutti { d'4 } is suppressed
    steps = [event.pitches[0].step for event in note_events]
    assert "D" not in steps         # tutti content suppressed
    assert "C" in steps and "E" in steps and "F" in steps


# ──────────────────────────────────────────────────────────────────────────────
# Multi-name tag lists: \tag #'(foo bar)
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_applies_multi_name_tag(multi_tag_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(multi_tag_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    steps = [event.pitches[0].step for event in note_events]
    # \removeWithTag #'foo suppresses \tag #'(foo bar) { c'4 } because foo is in the tag set
    assert "C" not in steps   # multi-tag (foo bar) suppressed because foo is removed
    assert "D" in steps       # \tag #'bar only → not suppressed
    assert "E" in steps       # \tag #'other → not suppressed
    assert "F" in steps       # untagged → always kept


# ──────────────────────────────────────────────────────────────────────────────
# Voice-separator shorthand polyphony: << { v1 } \\ { v2 } >>
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_splits_voice_separator(voice_separator_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(voice_separator_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    # melody = << { c' d' e' f' } \\ { e' f' g' a' } >> → 2 voices
    assert len(score.parts) == 1
    assert len(score.parts[0].voices) == 2

    voice1_notes = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]
    voice2_notes = [
        event
        for measure in score.parts[0].voices[1].measures
        for event in measure.events
        if event.is_note
    ]

    v1_steps = [e.pitches[0].step for e in voice1_notes]
    v2_steps = [e.pitches[0].step for e in voice2_notes]

    assert v1_steps == ["C", "D", "E", "F"]
    assert v2_steps == ["E", "F", "G", "A"]


def test_cli_convert_writes_voice_separator(
    repo_root: Path, voice_separator_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "voice_separator.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(voice_separator_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    # Both voices should be present — voice 2 notes use <chord> element after the first note
    assert xml.count("<note") >= 8   # 4 notes × 2 voices


# ──────────────────────────────────────────────────────────────────────────────
# Breath marks
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_breath_mark(breath_mark_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(breath_mark_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    note_events = [
        event
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        if event.is_note
    ]

    # f' has \breathe, g' does not, a' has \breathe
    assert note_events[3].breath_mark is True    # f' in measure 1
    assert note_events[4].breath_mark is False   # g' in measure 2
    assert note_events[5].breath_mark is True    # a' in measure 2


def test_cli_convert_writes_breath_mark(
    repo_root: Path, breath_mark_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "breath_mark.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(breath_mark_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<breath-mark />" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Tempo directions (text and metronome)
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_tempo_directions(tempo_change_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(tempo_change_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    all_directions = [
        direction
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        for direction in event.directions
    ]

    kinds = [d.kind for d in all_directions]
    assert "tempo" in kinds
    assert "metronome" in kinds

    tempo_dir = next(d for d in all_directions if d.kind == "tempo")
    assert tempo_dir.value == "Allegro"

    metronome_dir = next(d for d in all_directions if d.kind == "metronome")
    beat_unit, bpm = metronome_dir.value.split(":")
    assert beat_unit == "quarter"
    assert bpm == "120"


def test_cli_convert_writes_tempo_directions(
    repo_root: Path, tempo_change_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "tempo_change.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(tempo_change_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<words>Allegro</words>" in xml
    assert "<metronome" in xml
    assert "<beat-unit>quarter</beat-unit>" in xml
    assert "<per-minute>120</per-minute>" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Rehearsal marks
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_emits_rehearsal_marks(rehearsal_mark_entrypoint: Path) -> None:
    score = LilypondConverter().build_score(rehearsal_mark_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    all_directions = [
        direction
        for measure in score.parts[0].voices[0].measures
        for event in measure.events
        for direction in event.directions
    ]

    rehearsal_dirs = [d for d in all_directions if d.kind == "rehearsal"]
    assert len(rehearsal_dirs) == 3

    labels = [d.value for d in rehearsal_dirs]
    assert labels[0] == "A"     # \mark \default → auto "A"
    assert labels[1] == "B"     # \mark \default → auto "B"
    assert labels[2] == "Coda"  # \mark "Coda"


def test_cli_convert_writes_rehearsal_marks(
    repo_root: Path, rehearsal_mark_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "rehearsal_mark.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(rehearsal_mark_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<rehearsal>A</rehearsal>" in xml
    assert "<rehearsal>B</rehearsal>" in xml
    assert "<rehearsal>Coda</rehearsal>" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Mid-measure key changes
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_preserves_mid_measure_key_changes(key_change_entrypoint: Path) -> None:
    from ly2mxml.model.score import KeyChange

    score = LilypondConverter().build_score(key_change_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    measures = score.parts[0].voices[0].measures

    # Measure 0: C major (initial, no KeyChange recorded)
    assert measures[0].key_changes == []
    # Measure 1: G major (1 sharp)
    assert len(measures[1].key_changes) == 1
    assert measures[1].key_changes[0].fifths == 1
    assert measures[1].key_changes[0].mode == "major"
    # Measure 2: D minor (-1 flat relative, but in absolute: 1 flat BEFORE key change — depends on converter)
    assert len(measures[2].key_changes) == 1
    assert measures[2].key_changes[0].mode == "minor"


def test_cli_convert_writes_mid_measure_key_changes(
    repo_root: Path, key_change_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "key_change.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(key_change_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<fifths>1</fifths>" in xml   # G major
    assert "<mode>minor</mode>" in xml


# ──────────────────────────────────────────────────────────────────────────────
# Mid-measure time signature changes
# ──────────────────────────────────────────────────────────────────────────────

def test_build_score_preserves_mid_measure_time_changes(time_change_entrypoint: Path) -> None:
    from ly2mxml.model.score import TimeChange

    score = LilypondConverter().build_score(time_change_entrypoint)

    assert not any(diagnostic.severity == "error" for diagnostic in score.diagnostics)

    measures = score.parts[0].voices[0].measures

    # Measure 0: 4/4 (initial, no TimeChange)
    assert measures[0].time_changes == []
    # Measure 1: 3/4
    assert len(measures[1].time_changes) == 1
    assert measures[1].time_changes[0].numerator == 3
    assert measures[1].time_changes[0].denominator == 4
    # Measure 2: 6/8
    assert len(measures[2].time_changes) == 1
    assert measures[2].time_changes[0].numerator == 6
    assert measures[2].time_changes[0].denominator == 8


def test_cli_convert_writes_mid_measure_time_changes(
    repo_root: Path, time_change_entrypoint: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "time_change.musicxml"

    result = subprocess.run(
        [sys.executable, "-m", "ly2mxml", "convert", str(time_change_entrypoint), "-o", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    xml = output_path.read_text(encoding="utf-8")

    assert result.stderr.strip() == ""
    assert "<beats>3</beats>" in xml
    assert "<beat-type>4</beat-type>" in xml
    assert "<beats>6</beats>" in xml
    assert "<beat-type>8</beat-type>" in xml