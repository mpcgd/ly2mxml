from __future__ import annotations

from fractions import Fraction
from math import lcm
from pathlib import Path
import xml.etree.ElementTree as ET

from ly2mxml.model.score import Direction, Lyric, MusicEvent, Part, PartCombineMode, Pitch, Score, Voice
from ly2mxml.options import ExportOptions


class MusicXmlWriter:
    def write(
        self,
        score: Score,
        output_path: str | Path,
        export_options: ExportOptions | None = None,
        partcombine_mode: PartCombineMode | None = None,
    ) -> Path:
        export_options = self._resolve_export_options(export_options, partcombine_mode)
        path = Path(output_path)
        tree = ET.ElementTree(self.build_tree(score, export_options=export_options))
        path.write_text(self.to_string(score, export_options=export_options), encoding="utf-8")
        return path

    def to_string(
        self,
        score: Score,
        export_options: ExportOptions | None = None,
        partcombine_mode: PartCombineMode | None = None,
    ) -> str:
        export_options = self._resolve_export_options(export_options, partcombine_mode)
        root = self.build_tree(score, export_options=export_options)
        self._indent(root)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    def build_tree(
        self,
        score: Score,
        export_options: ExportOptions | None = None,
        partcombine_mode: PartCombineMode | None = None,
    ) -> ET.Element:
        export_options = self._resolve_export_options(export_options, partcombine_mode)
        root = ET.Element("score-partwise", version="4.0")
        rendered_parts = self._render_parts(score.parts, export_options.partcombine_mode)

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
        for part in rendered_parts:
            score_part = ET.SubElement(part_list, "score-part", id=part.id)
            part_name = ET.SubElement(score_part, "part-name")
            part_name.text = part.name
            if part.short_name:
                part_abbreviation = ET.SubElement(score_part, "part-abbreviation")
                part_abbreviation.text = part.short_name

        for part in rendered_parts:
            part_element = ET.SubElement(root, "part", id=part.id)
            measure_count = max((len(voice.measures) for voice in part.voices), default=0)
            multiple_rest_starts, multiple_rest_continuations = self._multiple_rest_map(part, measure_count)
            active_trill_lines: dict[str, set[tuple[tuple[str, int, int], ...]]] = {voice.id: set() for voice in part.voices}
            for measure_index in range(measure_count):
                measure_element = ET.SubElement(part_element, "measure", number=str(measure_index + 1))
                if measure_index == 0:
                    self._append_attributes(measure_element, part)
                    if part.tempo_text:
                        self._append_direction(measure_element, Direction(kind="tempo", value=part.tempo_text))
                if measure_index in multiple_rest_starts:
                    self._append_multiple_rest(measure_element, multiple_rest_starts[measure_index])

                if measure_index in multiple_rest_continuations:
                    continue

                for voice_index, voice in enumerate(part.voices):
                    measure = self._measure_for_voice(part, voice, measure_index)
                    if voice_index > 0:
                        backup = ET.SubElement(measure_element, "backup")
                        duration = ET.SubElement(backup, "duration")
                        duration.text = str(self._duration_to_units(part.measure_length, part.divisions))
                    self._append_measure_voice(measure_element, part, voice.id, measure, active_trill_lines[voice.id])
                barline_style = self._barline_for_measure(part, measure_index)
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

    def _multiple_rest_map(self, part: Part, measure_count: int) -> tuple[dict[int, int], set[int]]:
        if not part.voices or not all(voice.compress_empty_measures for voice in part.voices):
            return {}, set()

        starts: dict[int, int] = {}
        continuations: set[int] = set()
        measure_index = 0
        while measure_index < measure_count:
            if not self._is_multiple_rest_measure(part, measure_index):
                measure_index += 1
                continue

            run_end = measure_index + 1
            while run_end < measure_count and self._is_multiple_rest_measure(part, run_end):
                run_end += 1

            run_length = run_end - measure_index
            if run_length > 1:
                starts[measure_index] = run_length
                continuations.update(range(measure_index + 1, run_end))

            measure_index = run_end

        return starts, continuations

    def _is_multiple_rest_measure(self, part: Part, measure_index: int) -> bool:
        for voice in part.voices:
            measure = self._measure_for_voice(part, voice, measure_index)
            if len(measure.events) != 1:
                return False
            event = measure.events[0]
            if not event.is_rest or event.is_grace:
                return False
            if event.duration != part.measure_length or measure.duration != part.measure_length:
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
        first = parts[0]
        voices: list[Voice] = []
        divisions = 1
        for member_index, part in enumerate(parts, start=1):
            divisions = lcm(divisions, part.divisions)
            for voice in part.voices:
                voices.append(Voice(id=str(len(voices) + 1), source_name=voice.source_name, measures=voice.measures))

        return Part(
            id=first.id,
            name=first.combined_name or first.name,
            short_name=first.combined_short_name or first.short_name,
            clef_sign=first.clef_sign,
            clef_line=first.clef_line,
            time_signature=first.time_signature,
            key_fifths=first.key_fifths,
            key_mode=first.key_mode,
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

        clef = ET.SubElement(attributes, "clef")
        sign = ET.SubElement(clef, "sign")
        sign.text = part.clef_sign
        line = ET.SubElement(clef, "line")
        line.text = str(part.clef_line)

    def _append_measure_voice(
        self,
        measure_element: ET.Element,
        part: Part,
        voice_id: str,
        measure,
        active_trill_lines: set[tuple[tuple[str, int, int], ...]],
    ) -> None:
        for event in measure.events:
            for direction in event.directions:
                self._append_direction(measure_element, direction)
            trill_line_type = self._trill_line_type(event, active_trill_lines)
            self._append_event(measure_element, part, voice_id, measure, event, trill_line_type=trill_line_type)

    def _append_event(
        self,
        measure_element: ET.Element,
        part: Part,
        voice_id: str,
        measure,
        event: MusicEvent,
        trill_line_type: str | None = None,
    ) -> None:
        if event.is_rest:
            note = ET.SubElement(measure_element, "note")
            if event.is_cue:
                ET.SubElement(note, "cue")
            rest_attrs: dict[str, str] = {}
            if event.duration == part.measure_length and len(measure.events) == 1:
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
            if event.tuplet_start or event.tuplet_stop:
                notations = ET.SubElement(note, "notations")
                if event.tuplet_start:
                    ET.SubElement(notations, "tuplet", type="start", number="1")
                if event.tuplet_stop:
                    ET.SubElement(notations, "tuplet", type="stop", number="1")
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

            notations = None
            if event.tie_start:
                ET.SubElement(note, "tie", type="start")
                notations = self._ensure_notations(note, notations)
                ET.SubElement(notations, "tied", type="start")
            if event.tie_stop:
                ET.SubElement(note, "tie", type="stop")
                notations = self._ensure_notations(note, notations)
                ET.SubElement(notations, "tied", type="stop")
            if event.slur_start_count:
                notations = self._ensure_notations(note, notations)
                for _ in range(event.slur_start_count):
                    ET.SubElement(notations, "slur", type="start", number="1")
            if event.slur_stop_count:
                notations = self._ensure_notations(note, notations)
                for _ in range(event.slur_stop_count):
                    ET.SubElement(notations, "slur", type="stop", number="1")
            if event.tuplet_start:
                notations = self._ensure_notations(note, notations)
                ET.SubElement(notations, "tuplet", type="start", number="1")
            if event.tuplet_stop:
                notations = self._ensure_notations(note, notations)
                ET.SubElement(notations, "tuplet", type="stop", number="1")
            if event.ornaments or trill_line_type is not None:
                notations = self._ensure_notations(note, notations)
                ornaments = ET.SubElement(notations, "ornaments")
                for ornament in event.ornaments:
                    ET.SubElement(ornaments, ornament)
                if trill_line_type is not None:
                    ET.SubElement(ornaments, "wavy-line", type=trill_line_type)
            if event.articulations:
                notations = self._ensure_notations(note, notations)
                articulations = ET.SubElement(notations, "articulations")
                for articulation in event.articulations:
                    ET.SubElement(articulations, articulation)
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

    def _append_direction(self, measure_element: ET.Element, direction: Direction) -> None:
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
        else:
            words = ET.SubElement(direction_type, "words")
            words.text = direction.value

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
        bar_style = ET.SubElement(barline, "bar-style")
        bar_style.text = style

    def _measure_for_voice(self, part: Part, voice, measure_index: int):
        if measure_index < len(voice.measures):
            return voice.measures[measure_index]
        from ly2mxml.model.score import Measure, MusicEvent

        return Measure(
            number=measure_index + 1,
            events=[MusicEvent(duration=part.measure_length, is_rest=True)],
            duration=part.measure_length,
        )

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

    def _indent(self, element: ET.Element, level: int = 0) -> None:
        indent = "\n" + level * "  "
        if len(element):
            if not element.text or not element.text.strip():
                element.text = indent + "  "
            for child in element:
                self._indent(child, level + 1)
            if not element[-1].tail or not element[-1].tail.strip():
                element[-1].tail = indent
        if level and (not element.tail or not element.tail.strip()):
            element.tail = indent
