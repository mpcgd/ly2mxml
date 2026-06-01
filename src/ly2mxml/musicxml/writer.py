"""Serialize the intermediate score model as MusicXML.

The writer only consumes the resolved score model. It should not need to know
about the full LilyPond parser tree or re-interpret LilyPond-specific syntax.
"""

from __future__ import annotations

from fractions import Fraction
from math import lcm
from pathlib import Path
import xml.etree.ElementTree as ET

from ly2mxml.model.score import ClefChange, Direction, KeyChange, Lyric, MusicEvent, Part, PartCombineMode, Pitch, Score, TimeChange, Voice
from ly2mxml.options import ExportOptions


class MusicXmlWriter:
    """Render the internal score model as a MusicXML ``score-partwise`` tree."""

    def write(
        self,
        score: Score,
        output_path: str | Path,
        export_options: ExportOptions | None = None,
        partcombine_mode: PartCombineMode | None = None,
    ) -> Path:
        """Write one converted score to disk and return the resolved path."""

        export_options = self._resolve_export_options(export_options, partcombine_mode)
        path = Path(output_path)
        root = self.build_tree(score, export_options=export_options)
        path.write_text(self._serialize_root(root), encoding="utf-8")
        return path

    def to_string(
        self,
        score: Score,
        export_options: ExportOptions | None = None,
        partcombine_mode: PartCombineMode | None = None,
    ) -> str:
        """Render one converted score directly to a MusicXML string."""

        export_options = self._resolve_export_options(export_options, partcombine_mode)
        root = self.build_tree(score, export_options=export_options)
        return self._serialize_root(root)

    def _serialize_root(self, root: ET.Element) -> str:
        ET.indent(root, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    def build_tree(
        self,
        score: Score,
        export_options: ExportOptions | None = None,
        partcombine_mode: PartCombineMode | None = None,
    ) -> ET.Element:
        """Build the MusicXML tree for a converted score.

        The converter normalizes LilyPond semantics into the intermediate model;
        this method handles the XML-level concerns such as part lists, per-part
        divisions, measure backups, multiple rests, and note-direction output.
        """

        export_options = self._resolve_export_options(export_options, partcombine_mode)
        root = ET.Element("score-partwise", version="4.0")
        rendered_parts = self._render_parts(score.parts, export_options.partcombine_mode)
        score_measure_count = max((len(voice.measures) for part in rendered_parts for voice in part.voices), default=0)
        score_measure_durations = self._score_measure_durations(rendered_parts, score_measure_count)
        score_measure_barlines = self._score_measure_barlines(rendered_parts, score_measure_count)
        self._ensure_part_divisions(rendered_parts, score_measure_durations)

        if score.metadata.title:
            title = ET.SubElement(root, "movement-title")
            title.text = score.metadata.title

        identification = ET.SubElement(root, "identification")
        if score.metadata.composer:
            creator = ET.SubElement(identification, "creator", type="composer")
            creator.text = score.metadata.composer
        if score.metadata.arranger:
            arranger = ET.SubElement(identification, "creator", type="arranger")
            arranger.text = score.metadata.arranger
        encoding = ET.SubElement(identification, "encoding")
        software = ET.SubElement(encoding, "software")
        software.text = "ly2mxml"

        part_list = ET.SubElement(root, "part-list")
        group_number_stack: list[int] = []
        next_group_number = 1
        for part in rendered_parts:
            if part.group_start is not None:
                gn = next_group_number
                next_group_number += 1
                group_number_stack.append(gn)
                pg = ET.SubElement(part_list, "part-group", type="start", number=str(gn))
                ET.SubElement(pg, "group-symbol").text = part.group_start
                ET.SubElement(pg, "group-barline").text = "yes"
            score_part = ET.SubElement(part_list, "score-part", id=part.id)
            part_name = ET.SubElement(score_part, "part-name")
            part_name.text = part.name
            if part.short_name:
                part_abbreviation = ET.SubElement(score_part, "part-abbreviation")
                part_abbreviation.text = part.short_name
            if part.group_stop and group_number_stack:
                gn = group_number_stack.pop()
                ET.SubElement(part_list, "part-group", type="stop", number=str(gn))

        for part_index, part in enumerate(rendered_parts):
            part_element = ET.SubElement(root, "part", id=part.id)
            measure_count = score_measure_count
            # Multiple-rest compression is only applied when every exported
            # voice can safely participate, which avoids silently discarding
            # per-voice content such as directions or partial-measure rests.
            multiple_rest_starts, multiple_rest_continuations = self._multiple_rest_map(part, score_measure_durations)
            active_trill_lines: dict[str, set[tuple[tuple[str, int, int], ...]]] = {voice.id: set() for voice in part.voices}
            active_wedges: dict[str, str | None] = {voice.id: None for voice in part.voices}
            for measure_index in range(measure_count):
                measure_element = ET.SubElement(part_element, "measure", number=str(measure_index + 1))
                if measure_index == 0:
                    self._append_attributes(measure_element, part)
                    if part_index == 0 and part.tempo_text:
                        self._append_direction(measure_element, Direction(kind="tempo", value=part.tempo_text), None, None)
                if measure_index in multiple_rest_starts:
                    self._append_multiple_rest(measure_element, multiple_rest_starts[measure_index])

                if measure_index in multiple_rest_continuations:
                    continue

                if measure_index in multiple_rest_starts:
                    measure = self._measure_for_voice(part, part.voices[0], measure_index, score_measure_durations[measure_index])
                    active_wedges[part.voices[0].id] = self._append_measure_voice(
                        measure_element,
                        part,
                        part.voices[0].id,
                        measure,
                        self._clef_changes_for_measure(part, measure_index, score_measure_durations[measure_index]),
                        active_trill_lines[part.voices[0].id],
                        active_wedges[part.voices[0].id],
                        key_changes=self._key_changes_for_measure(part, measure_index, score_measure_durations[measure_index]),
                        time_changes=self._time_changes_for_measure(part, measure_index, score_measure_durations[measure_index]),
                    )
                    barline_style = self._barline_for_measure(part, measure_index) or score_measure_barlines[measure_index]
                    if barline_style is not None:
                        self._append_barline(measure_element, barline_style)
                    continue

                for voice_index, voice in enumerate(part.voices):
                    measure = self._measure_for_voice(part, voice, measure_index, score_measure_durations[measure_index])
                    if voice_index > 0:
                        # MusicXML voices in one measure are time-aligned with a
                        # backup element rather than interleaving unrelated note
                        # streams directly.
                        backup = ET.SubElement(measure_element, "backup")
                        duration = ET.SubElement(backup, "duration")
                        duration.text = str(self._duration_to_units(score_measure_durations[measure_index], part.divisions))
                    active_wedges[voice.id] = self._append_measure_voice(
                        measure_element,
                        part,
                        voice.id,
                        measure,
                        self._clef_changes_for_measure(part, measure_index, score_measure_durations[measure_index]) if voice_index == 0 else (),
                        active_trill_lines[voice.id],
                        active_wedges[voice.id],
                        key_changes=self._key_changes_for_measure(part, measure_index, score_measure_durations[measure_index]) if voice_index == 0 else (),
                        time_changes=self._time_changes_for_measure(part, measure_index, score_measure_durations[measure_index]) if voice_index == 0 else (),
                    )
                barline_style = self._barline_for_measure(part, measure_index) or score_measure_barlines[measure_index]
                if barline_style is not None:
                    self._append_barline(measure_element, barline_style)

        return root

    def _resolve_export_options(
        self,
        export_options: ExportOptions | None,
        partcombine_mode: PartCombineMode | None,
    ) -> ExportOptions:
        if export_options is None:
            if partcombine_mode is None:
                return ExportOptions()
            return ExportOptions(partcombine_mode=partcombine_mode)
        if partcombine_mode is not None and export_options.partcombine_mode != partcombine_mode:
            return ExportOptions(partcombine_mode=partcombine_mode, cue_mode=export_options.cue_mode)
        return export_options

    def _multiple_rest_map(self, part: Part, measure_durations: list[Fraction]) -> tuple[dict[int, int], set[int]]:
        """Locate runs of full-measure rests eligible for MusicXML compression."""

        if not part.voices or not all(voice.compress_empty_measures for voice in part.voices):
            return {}, set()

        starts: dict[int, int] = {}
        continuations: set[int] = set()
        measure_count = len(measure_durations)
        measure_index = 0
        while measure_index < measure_count:
            if not self._is_multiple_rest_measure(part, measure_index, measure_durations[measure_index]):
                measure_index += 1
                continue

            run_end = measure_index + 1
            while run_end < measure_count and self._is_multiple_rest_measure(part, run_end, measure_durations[run_end]):
                run_end += 1

            run_length = run_end - measure_index
            if run_length > 1:
                starts[measure_index] = run_length
                continuations.update(range(measure_index + 1, run_end))

            measure_index = run_end

        return starts, continuations

    def _is_multiple_rest_measure(self, part: Part, measure_index: int, expected_duration: Fraction) -> bool:
        if expected_duration != part.measure_length:
            return False
        for voice in part.voices:
            measure = self._measure_for_voice(part, voice, measure_index, expected_duration)
            if measure.clef_changes:
                return False
            if len(measure.events) != 1:
                return False
            event = measure.events[0]
            if not event.is_rest or event.is_grace:
                return False
            if event.duration != expected_duration or measure.duration != expected_duration:
                return False
            if event.directions or event.articulations or event.ornaments or event.lyrics:
                return False
        return True

    def _append_multiple_rest(self, measure_element: ET.Element, measure_count: int) -> None:
        attributes = self._ensure_attributes(measure_element)
        measure_style = ET.SubElement(attributes, "measure-style")
        multiple_rest = ET.SubElement(measure_style, "multiple-rest")
        multiple_rest.text = str(measure_count)

    def _render_parts(self, parts: list[Part], partcombine_mode: PartCombineMode) -> list[Part]:
        """Return the part list exactly as it should appear in MusicXML output."""

        if partcombine_mode == "separate":
            return parts

        rendered_parts: list[Part] = []
        index = 0
        while index < len(parts):
            part = parts[index]
            if part.combine_group is None:
                rendered_parts.append(part)
                index += 1
                continue

            grouped_parts = [part]
            index += 1
            while index < len(parts) and parts[index].combine_group == part.combine_group:
                grouped_parts.append(parts[index])
                index += 1
            rendered_parts.append(self._merge_partcombine_group(grouped_parts))

        return rendered_parts

    def _merge_partcombine_group(self, parts: list[Part]) -> Part:
        """Merge one planned partCombine group back into a multi-voice part."""

        first = parts[0]
        voices: list[Voice] = []
        divisions = 1
        for member_index, part in enumerate(parts, start=1):
            divisions = lcm(divisions, part.divisions)
            for voice in part.voices:
                voices.append(
                    Voice(
                        id=str(len(voices) + 1),
                        source_name=voice.source_name,
                        measures=voice.measures,
                        compress_empty_measures=voice.compress_empty_measures,
                    )
                )

        return Part(
            id=first.id,
            name=first.combined_name or first.name,
            short_name=first.combined_short_name or first.short_name,
            clef_sign=first.clef_sign,
            clef_line=first.clef_line,
            time_signature=first.time_signature,
            key_fifths=first.key_fifths,
            key_mode=first.key_mode,
            clef_octave_change=first.clef_octave_change,
            tempo_text=first.tempo_text,
            voices=voices,
            divisions=divisions,
        )

    def _append_attributes(self, measure_element: ET.Element, part: Part) -> None:
        attributes = ET.SubElement(measure_element, "attributes")
        divisions = ET.SubElement(attributes, "divisions")
        divisions.text = str(part.divisions)

        key = ET.SubElement(attributes, "key")
        fifths = ET.SubElement(key, "fifths")
        fifths.text = str(part.key_fifths)
        mode = ET.SubElement(key, "mode")
        mode.text = part.key_mode

        time = ET.SubElement(attributes, "time")
        beats = ET.SubElement(time, "beats")
        beat_type = ET.SubElement(time, "beat-type")
        beats.text = str(part.time_signature[0])
        beat_type.text = str(part.time_signature[1])

        self._append_clef(attributes, part.clef_sign, part.clef_line, part.clef_octave_change)

    def _append_measure_voice(
        self,
        measure_element: ET.Element,
        part: Part,
        voice_id: str,
        measure,
        clef_changes: tuple[ClefChange, ...],
        active_trill_lines: set[tuple[tuple[str, int, int], ...]],
        active_wedge: str | None,
        key_changes: tuple[KeyChange, ...] = (),
        time_changes: tuple[TimeChange, ...] = (),
    ) -> str | None:
        """Append one voice's measure content and return the updated wedge state."""

        clef_index = 0
        key_index = 0
        time_index = 0
        elapsed = Fraction(0, 1)
        for event in measure.events:
            while clef_index < len(clef_changes) and clef_changes[clef_index].offset == elapsed:
                self._append_clef_change(measure_element, clef_changes[clef_index])
                clef_index += 1
            while key_index < len(key_changes) and key_changes[key_index].offset == elapsed:
                self._append_key_change(measure_element, key_changes[key_index])
                key_index += 1
            while time_index < len(time_changes) and time_changes[time_index].offset == elapsed:
                self._append_time_change(measure_element, time_changes[time_index])
                time_index += 1
            for direction in event.directions:
                active_wedge = self._append_direction(measure_element, direction, active_wedge, voice_id)
            trill_line_type = self._trill_line_type(event, active_trill_lines)
            self._append_event(measure_element, part, voice_id, measure, event, trill_line_type=trill_line_type)
            if not event.is_grace:
                elapsed += event.duration

        while clef_index < len(clef_changes) and clef_changes[clef_index].offset == elapsed:
            self._append_clef_change(measure_element, clef_changes[clef_index])
            clef_index += 1
        while key_index < len(key_changes) and key_changes[key_index].offset == elapsed:
            self._append_key_change(measure_element, key_changes[key_index])
            key_index += 1
        while time_index < len(time_changes) and time_changes[time_index].offset == elapsed:
            self._append_time_change(measure_element, time_changes[time_index])
            time_index += 1
        return active_wedge

    def _append_clef_change(self, measure_element: ET.Element, clef_change: ClefChange) -> None:
        attributes = ET.SubElement(measure_element, "attributes")
        self._append_clef(attributes, clef_change.sign, clef_change.line, clef_change.octave_change)

    def _append_clef(self, attributes: ET.Element, sign: str, line: int, octave_change: int | None) -> None:
        clef = ET.SubElement(attributes, "clef")
        sign_element = ET.SubElement(clef, "sign")
        sign_element.text = sign
        line_element = ET.SubElement(clef, "line")
        line_element.text = str(line)
        if octave_change is not None:
            # MusicXML 4.0 allows clef-octave-change values from -3 to 3.
            clamped = max(-3, min(3, octave_change))
            octave_element = ET.SubElement(clef, "clef-octave-change")
            octave_element.text = str(clamped)

    def _append_event(
        self,
        measure_element: ET.Element,
        part: Part,
        voice_id: str,
        measure,
        event: MusicEvent,
        trill_line_type: str | None = None,
    ) -> None:
        """Serialize one note or rest event, including its notations and lyrics."""

        if event.is_rest:
            note = ET.SubElement(measure_element, "note")
            if event.is_cue:
                ET.SubElement(note, "cue")
            rest_attrs: dict[str, str] = {}
            if event.duration == measure.duration and len(measure.events) == 1:
                rest_attrs["measure"] = "yes"
            ET.SubElement(note, "rest", rest_attrs)
            if not event.is_grace:
                duration = ET.SubElement(note, "duration")
                duration.text = str(self._duration_to_units(event.duration, part.divisions))
            voice = ET.SubElement(note, "voice")
            voice.text = voice_id
            note_type, dots = self._duration_type_and_dots(event.duration)
            if note_type:
                type_element = ET.SubElement(note, "type")
                type_element.text = note_type
            for _ in range(dots):
                ET.SubElement(note, "dot")
            if event.time_modification:
                self._append_time_modification(note, event.time_modification)
            if event.tuplet_start or event.tuplet_stop or event.tremolo_slashes:
                rest_notations = ET.SubElement(note, "notations")
                if event.tuplet_start:
                    ET.SubElement(rest_notations, "tuplet", type="start", number="1")
                if event.tuplet_stop:
                    ET.SubElement(rest_notations, "tuplet", type="stop", number="1")
                if event.tremolo_slashes:
                    ornaments = ET.SubElement(rest_notations, "ornaments")
                    tremolo = ET.SubElement(ornaments, "tremolo", type=event.tremolo_type or "single")
                    tremolo.text = str(event.tremolo_slashes)
            return

        for index, pitch in enumerate(event.pitches):
            note = ET.SubElement(measure_element, "note")
            if event.is_grace:
                grace_attributes = {"slash": "yes"} if event.grace_slash else {}
                ET.SubElement(note, "grace", grace_attributes)
            if event.is_cue:
                ET.SubElement(note, "cue")
            if index > 0:
                ET.SubElement(note, "chord")
            self._append_pitch(note, pitch)
            if not event.is_grace and index == 0:
                duration = ET.SubElement(note, "duration")
                duration.text = str(self._duration_to_units(event.duration, part.divisions))
            if event.tie_start:
                ET.SubElement(note, "tie", type="start")
            if event.tie_stop:
                ET.SubElement(note, "tie", type="stop")
            voice = ET.SubElement(note, "voice")
            voice.text = voice_id
            note_type, dots = self._duration_type_and_dots(event.duration)
            if note_type:
                type_element = ET.SubElement(note, "type")
                type_element.text = note_type
            for _ in range(dots):
                ET.SubElement(note, "dot")
            if event.time_modification:
                self._append_time_modification(note, event.time_modification)
            if event.stem and index == 0:
                stem_elem = ET.SubElement(note, "stem")
                stem_elem.text = event.stem

            notations = None
            if event.tie_start:
                notations = self._ensure_notations(note, notations)
                ET.SubElement(notations, "tied", type="start")
            if event.tie_stop:
                notations = self._ensure_notations(note, notations)
                ET.SubElement(notations, "tied", type="stop")
            if event.slur_start_count:
                notations = self._ensure_notations(note, notations)
                for _ in range(event.slur_start_count):
                    ET.SubElement(notations, "slur", type="start", number=voice_id)
            if event.slur_stop_count:
                notations = self._ensure_notations(note, notations)
                for _ in range(event.slur_stop_count):
                    ET.SubElement(notations, "slur", type="stop", number=voice_id)
            if event.phrase_slur_start_count:
                notations = self._ensure_notations(note, notations)
                for _ in range(event.phrase_slur_start_count):
                    ET.SubElement(notations, "slur", type="start", number="2")
            if event.phrase_slur_stop_count:
                notations = self._ensure_notations(note, notations)
                for _ in range(event.phrase_slur_stop_count):
                    ET.SubElement(notations, "slur", type="stop", number="2")
            if event.tuplet_start:
                notations = self._ensure_notations(note, notations)
                ET.SubElement(notations, "tuplet", type="start", number="1")
            if event.tuplet_stop:
                notations = self._ensure_notations(note, notations)
                ET.SubElement(notations, "tuplet", type="stop", number="1")
            if event.ornaments or trill_line_type is not None or event.tremolo_slashes:
                notations = self._ensure_notations(note, notations)
                ornaments = ET.SubElement(notations, "ornaments")
                for ornament in event.ornaments:
                    ET.SubElement(ornaments, ornament)
                if trill_line_type is not None:
                    ET.SubElement(ornaments, "wavy-line", type=trill_line_type)
                if event.tremolo_slashes and index == 0:
                    tremolo = ET.SubElement(ornaments, "tremolo", type=event.tremolo_type or "single")
                    tremolo.text = str(event.tremolo_slashes)
            if event.technical:
                notations = self._ensure_notations(note, notations)
                technical_elem = ET.SubElement(notations, "technical")
                for technical_mark in event.technical:
                    ET.SubElement(technical_elem, technical_mark)
            if event.articulations or (event.breath_mark and index == 0):
                notations = self._ensure_notations(note, notations)
                articulations = ET.SubElement(notations, "articulations")
                for articulation in event.articulations:
                    ET.SubElement(articulations, articulation)
                if event.breath_mark and index == 0:
                    ET.SubElement(articulations, "breath-mark")
            if event.fermatas:
                notations = self._ensure_notations(note, notations)
                for fermata_shape in event.fermatas:
                    fermata_elem = ET.SubElement(notations, "fermata", type="upright")
                    if fermata_shape:
                        fermata_elem.text = fermata_shape
            if index == 0:
                if event.arpeggiate:
                    notations = self._ensure_notations(note, notations)
                    ET.SubElement(notations, "arpeggiate")
                if event.glissando_start:
                    notations = self._ensure_notations(note, notations)
                    ET.SubElement(notations, "glissando", type="start", number="1")
                if event.glissando_stop:
                    notations = self._ensure_notations(note, notations)
                    ET.SubElement(notations, "glissando", type="stop", number="1")
            for lyric in event.lyrics:
                self._append_lyric(note, lyric)

    def _append_pitch(self, note_element: ET.Element, pitch: Pitch) -> None:
        pitch_element = ET.SubElement(note_element, "pitch")
        step = ET.SubElement(pitch_element, "step")
        step.text = pitch.step
        if pitch.alter:
            alter = ET.SubElement(pitch_element, "alter")
            alter.text = str(pitch.alter)
        octave = ET.SubElement(pitch_element, "octave")
        octave.text = str(pitch.octave)

    def _append_direction(
        self,
        measure_element: ET.Element,
        direction: Direction,
        active_wedge: str | None,
        voice_id: str | None,
    ) -> str | None:
        """Serialize one direction and keep wedge state consistent across notes."""

        if direction.kind == "dynamic" and active_wedge is not None:
            active_wedge = self._append_direction(
                measure_element,
                Direction(kind="wedge", value="stop"),
                active_wedge,
                voice_id,
            )

        if direction.kind == "wedge":
            if direction.value == "stop":
                if active_wedge is None:
                    return None
                next_active_wedge = None
            else:
                next_active_wedge = direction.value
        else:
            next_active_wedge = active_wedge

        direction_attributes: dict[str, str] = {}
        if direction.kind == "octave-shift":
            placement, _, _ = direction.value.split(":", 2)
            direction_attributes["placement"] = placement
        direction_element = ET.SubElement(measure_element, "direction", direction_attributes)
        direction_type = ET.SubElement(direction_element, "direction-type")
        if direction.kind == "dynamic":
            dynamics = ET.SubElement(direction_type, "dynamics")
            ET.SubElement(dynamics, direction.value)
        elif direction.kind == "wedge":
            ET.SubElement(direction_type, "wedge", type=direction.value)
        elif direction.kind == "octave-shift":
            _, shift_type, size = direction.value.split(":", 2)
            ET.SubElement(direction_type, "octave-shift", type=shift_type, size=size)
        elif direction.kind == "rehearsal":
            rehearsal = ET.SubElement(direction_type, "rehearsal")
            rehearsal.text = direction.value
        elif direction.kind == "coda":
            ET.SubElement(direction_type, "coda")
        elif direction.kind == "segno":
            ET.SubElement(direction_type, "segno")
        elif direction.kind == "metronome":
            beat_unit, _, bpm = direction.value.partition(":")
            metronome = ET.SubElement(direction_type, "metronome", parentheses="no")
            beat_unit_elem = ET.SubElement(metronome, "beat-unit")
            beat_unit_elem.text = beat_unit
            per_minute = ET.SubElement(metronome, "per-minute")
            per_minute.text = bpm
        else:
            words = ET.SubElement(direction_type, "words")
            words.text = direction.value
        if voice_id is not None:
            voice = ET.SubElement(direction_element, "voice")
            voice.text = voice_id
        return next_active_wedge

    def _append_time_modification(self, note_element: ET.Element, modification: tuple[int, int]) -> None:
        time_modification = ET.SubElement(note_element, "time-modification")
        actual_notes = ET.SubElement(time_modification, "actual-notes")
        actual_notes.text = str(modification[0])
        normal_notes = ET.SubElement(time_modification, "normal-notes")
        normal_notes.text = str(modification[1])

    def _append_lyric(self, note_element: ET.Element, lyric: Lyric) -> None:
        lyric_attributes: dict[str, str] = {}
        if lyric.number is not None:
            lyric_attributes["number"] = str(lyric.number)
        lyric_element = ET.SubElement(note_element, "lyric", lyric_attributes)
        if lyric.syllabic:
            syllabic = ET.SubElement(lyric_element, "syllabic")
            syllabic.text = lyric.syllabic
        text = ET.SubElement(lyric_element, "text")
        text.text = lyric.text
        if lyric.extend:
            ET.SubElement(lyric_element, "extend")

    def _ensure_notations(self, note_element: ET.Element, notations: ET.Element | None) -> ET.Element:
        if notations is None:
            notations = ET.SubElement(note_element, "notations")
        return notations

    def _trill_line_type(
        self,
        event: MusicEvent,
        active_trill_lines: set[tuple[tuple[str, int, int], ...]],
    ) -> str | None:
        """Track trill-line continuity across tied notes with the same pitch set."""

        signature = self._event_signature(event)
        if signature is None:
            return None

        has_trill = "trill-mark" in event.ornaments
        is_active = signature in active_trill_lines

        if has_trill and event.tie_start and not is_active:
            active_trill_lines.add(signature)
            return "start"

        if is_active and event.tie_stop and event.tie_start:
            return "continue"

        if is_active and event.tie_stop:
            active_trill_lines.remove(signature)
            return "stop"

        return None

    def _event_signature(self, event: MusicEvent) -> tuple[tuple[str, int, int], ...] | None:
        if event.is_rest or not event.pitches:
            return None
        return tuple((pitch.step, pitch.alter, pitch.octave) for pitch in event.pitches)

    def _ensure_attributes(self, measure_element: ET.Element) -> ET.Element:
        attributes = measure_element.find("attributes")
        if attributes is None:
            attributes = ET.SubElement(measure_element, "attributes")
        return attributes

    def _barline_for_measure(self, part: Part, measure_index: int) -> str | None:
        for voice in part.voices:
            if measure_index < len(voice.measures):
                barline = voice.measures[measure_index].right_barline
                if barline is not None:
                    return barline
        return None

    def _append_barline(self, measure_element: ET.Element, style: str) -> None:
        barline = ET.SubElement(measure_element, "barline", location="right")
        if ":" in style:
            bar_style_text, repeat_direction = style.split(":", 1)
        else:
            bar_style_text, repeat_direction = style, None
        bar_style_elem = ET.SubElement(barline, "bar-style")
        bar_style_elem.text = bar_style_text
        if repeat_direction:
            ET.SubElement(barline, "repeat", direction=repeat_direction)

    def _score_measure_durations(self, parts: list[Part], measure_count: int) -> list[Fraction]:
        durations: list[Fraction] = []
        for measure_index in range(measure_count):
            duration = max(
                (
                    voice.measures[measure_index].duration
                    for part in parts
                    for voice in part.voices
                    if measure_index < len(voice.measures)
                ),
                default=Fraction(0, 1),
            )
            if duration == 0 and parts:
                duration = parts[0].measure_length
            durations.append(duration)
        return durations

    def _score_measure_barlines(self, parts: list[Part], measure_count: int) -> list[str | None]:
        barlines: list[str | None] = []
        for measure_index in range(measure_count):
            barline_style = next(
                (
                    self._barline_for_measure(part, measure_index)
                    for part in parts
                    if self._barline_for_measure(part, measure_index) is not None
                ),
                None,
            )
            barlines.append(barline_style)
        return barlines

    def _ensure_part_divisions(self, parts: list[Part], measure_durations: list[Fraction]) -> None:
        required_divisions = 1
        for duration in measure_durations:
            required_divisions = lcm(required_divisions, (duration * 4).denominator)
        for part in parts:
            part.divisions = lcm(part.divisions, required_divisions)

    def _measure_for_voice(self, part: Part, voice, measure_index: int, expected_duration: Fraction):
        if measure_index < len(voice.measures):
            return voice.measures[measure_index]
        from ly2mxml.model.score import Measure, MusicEvent

        return Measure(
            number=measure_index + 1,
            events=[MusicEvent(duration=expected_duration, is_rest=True)],
            duration=expected_duration,
        )

    def _clef_changes_for_measure(self, part: Part, measure_index: int, expected_duration: Fraction) -> tuple[ClefChange, ...]:
        for voice in part.voices:
            measure = self._measure_for_voice(part, voice, measure_index, expected_duration)
            if measure.clef_changes:
                return tuple(measure.clef_changes)
        return ()

    def _key_changes_for_measure(self, part: Part, measure_index: int, expected_duration: Fraction) -> tuple[KeyChange, ...]:
        for voice in part.voices:
            measure = self._measure_for_voice(part, voice, measure_index, expected_duration)
            if measure.key_changes:
                return tuple(measure.key_changes)
        return ()

    def _time_changes_for_measure(self, part: Part, measure_index: int, expected_duration: Fraction) -> tuple[TimeChange, ...]:
        for voice in part.voices:
            measure = self._measure_for_voice(part, voice, measure_index, expected_duration)
            if measure.time_changes:
                return tuple(measure.time_changes)
        return ()

    def _append_key_change(self, measure_element: ET.Element, key_change: KeyChange) -> None:
        attributes = ET.SubElement(measure_element, "attributes")
        key = ET.SubElement(attributes, "key")
        fifths = ET.SubElement(key, "fifths")
        fifths.text = str(key_change.fifths)
        mode = ET.SubElement(key, "mode")
        mode.text = key_change.mode

    def _append_time_change(self, measure_element: ET.Element, time_change: TimeChange) -> None:
        attributes = ET.SubElement(measure_element, "attributes")
        time = ET.SubElement(attributes, "time")
        beats = ET.SubElement(time, "beats")
        beats.text = str(time_change.numerator)
        beat_type = ET.SubElement(time, "beat-type")
        beat_type.text = str(time_change.denominator)

    def _duration_to_units(self, duration: Fraction, divisions: int) -> int:
        return int(duration * 4 * divisions)

    def _duration_type_and_dots(self, duration: Fraction) -> tuple[str | None, int]:
        base_values = [
            ("whole", Fraction(1, 1)),
            ("half", Fraction(1, 2)),
            ("quarter", Fraction(1, 4)),
            ("eighth", Fraction(1, 8)),
            ("16th", Fraction(1, 16)),
            ("32nd", Fraction(1, 32)),
            ("64th", Fraction(1, 64)),
            ("128th", Fraction(1, 128)),
        ]
        for type_name, base in base_values:
            running = Fraction(0, 1)
            for dots in range(4):
                running += base / (2**dots)
                if running == duration:
                    return type_name, dots
        return None, 0


