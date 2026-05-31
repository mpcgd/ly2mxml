"""Voice-building logic for the LilyPond-to-MusicXML converter.

This module owns the semantic assembly of a single LilyPond voice into the
intermediate model.  It is driven by the flattened node stream produced by
:mod:`ly2mxml.linearizer` and writes into the mutable measure/event model
defined in :mod:`ly2mxml.model.score`.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import Iterable, Mapping

from ly.music import items

from ly2mxml._types import (
    _BarlineChange,
    _CueInsertion,
    _FlattenedNode,
    _LyricToken,
    _OttavaChange,
    _PartialDuration,
    _RehearsalMark,
    _SecondaryVoiceBlocks,
    _VoiceBuildState,
    _WalkState,
)
from ly2mxml.diagnostics import Diagnostic, location_from_item
from ly2mxml.linearizer import Linearizer
from ly2mxml.model.score import (
    ClefChange,
    Direction,
    KeyChange,
    Lyric,
    Measure,
    MusicEvent,
    Part,
    Pitch,
    TimeChange,
    Voice,
)
from ly2mxml.options import ExportOptions
from ly2mxml import state_resolver as _sr

# ---------------------------------------------------------------------------
# Voice-building constants
# ---------------------------------------------------------------------------

DYNAMIC_MARKS: dict[str, str] = {
    "\\ppp": "ppp",
    "\\pppp": "pppp",
    "\\pp": "pp",
    "\\p": "p",
    "\\mp": "mp",
    "\\mf": "mf",
    "\\f": "f",
    "\\ff": "ff",
    "\\fff": "fff",
    "\\ffff": "ffff",
    "\\fp": "fp",
    "\\fz": "fz",
    "\\rf": "rf",
    "\\rfz": "rfz",
    "\\sf": "sf",
    "\\sfp": "sfp",
    "\\sfpp": "sfpp",
    "\\sfz": "sfz",
    "\\sff": "sff",
    "\\sffz": "sffz",
}

TEXT_DYNAMICS: dict[str, str] = {
    "\\cresc": "cresc.",
    "\\dim": "dim.",
    "\\decresc": "decresc.",
}

WEDGE_DYNAMICS: dict[str, str] = {
    "\\<": "crescendo",
    "\\>": "diminuendo",
    "\\!": "stop",
}

ARTICULATION_MAP: dict[str, str] = {
    ".": "staccato",
    "!": "staccatissimo",
    ">": "accent",
    "-": "tenuto",
    "_": "detached-legato",
    "^": "strong-accent",
    "\\staccato": "staccato",
    "\\staccatissimo": "staccatissimo",
    "\\accent": "accent",
    "\\tenuto": "tenuto",
    "\\marcato": "strong-accent",
    "\\portato": "detached-legato",
    "\\espressivo": "soft-accent",
}

ORNAMENT_MAP: dict[str, str] = {
    "\\trill": "trill-mark",
    "\\mordent": "mordent",
    "\\prall": "inverted-mordent",
    "\\turn": "turn",
    "\\reverseturn": "inverted-turn",
    "\\prallmordent": "mordent",
    "\\prallprall": "inverted-mordent",
    "\\downmordent": "mordent",
    "\\upmordent": "inverted-mordent",
    "\\tremblement": "trill-mark",
    "\\haydn": "haydn",
}

FERMATA_MAP: dict[str, str] = {
    "\\fermata": "",
    "\\shortfermata": "square",
    "\\longfermata": "angled",
    "\\verylongfermata": "square",
}

TECHNICAL_MAP: dict[str, str] = {
    "\\upbow": "up-bow",
    "\\downbow": "down-bow",
    "\\stopped": "stopped",
    "\\snappizzicato": "snap-pizzicato",
    "\\open": "open-string",
    "\\flageolet": "harmonic",
    "\\thumb": "thumb-position",
    "\\lheel": "heel",
    "\\rheel": "heel",
    "\\ltoe": "toe",
    "\\rtoe": "toe",
    "\\naturalHarmonic": "harmonic",
    "\\artificialHarmonic": "harmonic",
}

VOICE_COMMAND_STEMS: dict[str, str | None] = {
    "\\voiceOne": "up",
    "\\voiceTwo": "down",
    "\\voiceThree": "up",
    "\\voiceFour": "down",
    "\\stemUp": "up",
    "\\stemDown": "down",
    "\\stemNeutral": None,
    "\\oneVoice": None,
}

PERFORMANCE_TEXT_MARKS: dict[str, str] = {
    "\\arco": "arco",
    "\\pizzicato": "pizz.",
    "\\colLegno": "col legno",
    "\\sulTasto": "sul tasto",
    "\\sulPonticello": "sul ponticello",
}

CODA_SEGNO_COMMANDS: dict[str, str] = {
    "\\coda": "coda",
    "\\segno": "segno",
    "\\codaMark": "coda",
    "\\segnoCodaMark": "segno",
}

# Commands explicitly ignored during voice building.
IGNORED_COMMANDS: frozenset[str] = frozenset({"\\compressEmptyMeasures"})

# ---------------------------------------------------------------------------
# VoiceBuilder
# ---------------------------------------------------------------------------


class VoiceBuilder:
    """Assemble a LilyPond music node into the intermediate :class:`Voice` model.

    One :class:`VoiceBuilder` instance is created per :meth:`build_score` call
    so that shared counters (rehearsal marks, quote-voice cache) are reset
    automatically for each conversion.
    """

    def __init__(self, linearizer: Linearizer, export_options: ExportOptions) -> None:
        self.linearizer = linearizer
        self.export_options = export_options
        self._rehearsal_mark_counter: int = 0
        self._quote_voice_cache: dict[tuple[str, Fraction], Voice] = {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def build_voice(
        self,
        voice_id: str,
        source_name: str,
        music_node: items.Item,
        measure_length: Fraction,
        assignments: dict[str, items.Item | None],
        quote_sources: dict[str, items.Item],
        diagnostics: list[Diagnostic],
        allow_cues: bool = True,
        initial_state: _WalkState | None = None,
        initial_clef: tuple[str, int, int | None] | None = None,
        initial_key_fifths: int = 0,
        initial_key_mode: str = "major",
        initial_time_signature: tuple[int, int] = (4, 4),
        out_extra_voices: list[Voice] | None = None,
    ) -> Voice:
        """Flatten one LilyPond music source into a linear exported voice."""

        voice = Voice(id=voice_id, source_name=source_name)
        state = _VoiceBuildState(
            current_measure=Measure(number=1),
            current_clef=initial_clef or _sr.DEFAULT_CLEF,
            current_key_fifths=initial_key_fifths,
            current_key_mode=initial_key_mode,
            current_time_signature=initial_time_signature,
        )

        walk_state = replace(
            initial_state or _WalkState(),
            allow_cues=allow_cues,
            measure_length=measure_length,
        )
        _partial_full_length: Fraction | None = None

        for flattened in self.linearizer._iter_linear_nodes(music_node, walk_state):
            if _partial_full_length is not None and voice.measures:
                measure_length = _partial_full_length
                _partial_full_length = None

            node = flattened.node
            is_grace = flattened.is_grace

            if isinstance(node, _OttavaChange):
                state.pending_directions.extend(
                    self._ottava_directions(node.value, state.active_ottava)
                )
                state.active_ottava = node.value or None

            elif isinstance(node, _BarlineChange):
                style = self._barline_style(node.value)
                if style is not None:
                    self._apply_voice_barline(voice, state, style)

            elif isinstance(node, _RehearsalMark):
                label = node.label
                if label is None:
                    self._rehearsal_mark_counter += 1
                    label = chr(ord("A") + (self._rehearsal_mark_counter - 1) % 26)
                self._add_voice_direction(state, Direction(kind="rehearsal", value=label))

            elif isinstance(node, _CueInsertion):
                self._add_cue_insertion(
                    voice,
                    state,
                    node,
                    measure_length,
                    source_name,
                    assignments,
                    quote_sources,
                    diagnostics,
                )

            elif isinstance(node, items.Clef):
                self._add_voice_clef_change(
                    voice, state, node, measure_length, source_name, diagnostics
                )

            elif isinstance(node, items.Tempo):
                for direction in self._tempo_directions(node):
                    self._add_voice_direction(state, direction)

            elif isinstance(node, items.KeySignature):
                pitch = node.pitch()
                new_mode = node.mode() or "major"
                new_fifths = _sr.key_fifths(pitch, new_mode, flattened.transpose_specs)
                if new_fifths != state.current_key_fifths or new_mode != state.current_key_mode:
                    state.current_measure.key_changes.append(
                        KeyChange(
                            offset=state.elapsed,
                            fifths=new_fifths,
                            mode=new_mode,
                        )
                    )
                    state.current_key_fifths = new_fifths
                    state.current_key_mode = new_mode

            elif isinstance(node, items.TimeSignature):
                fraction = node.fraction()
                if fraction:
                    new_num = node.numerator()
                    new_den = int(1 / fraction)
                    if (new_num, new_den) != state.current_time_signature:
                        state.current_measure.time_changes.append(
                            TimeChange(
                                offset=state.elapsed,
                                numerator=new_num,
                                denominator=new_den,
                            )
                        )
                        state.current_time_signature = (new_num, new_den)
                        measure_length = Fraction(new_num, new_den)

            elif isinstance(node, items.Note):
                state.attachment_event = None
                source_pitch = (
                    flattened.resolved_pitches[0]
                    if flattened.resolved_pitches
                    else node.pitch
                )
                event = self._build_voice_event(
                    duration=self.linearizer._duration_from_node(
                        node.duration, flattened.scale
                    ),
                    pitches=[_sr.to_pitch(source_pitch, flattened.transpose_specs)],
                    flattened=flattened,
                    pending_directions=state.pending_directions,
                    stem=state.current_stem,
                )
                state.pending_directions.clear()
                if state.pending_glissando_stop and not flattened.is_grace:
                    event.glissando_stop = True
                    state.pending_glissando_stop = False
                self._add_voice_event(
                    voice, state, event, measure_length, source_name, diagnostics, node
                )

            elif isinstance(node, items.Chord):
                state.attachment_event = None
                chord_pitches = flattened.resolved_pitches or tuple(
                    child.pitch for child in node if isinstance(child, items.Note)
                )
                pitches = [
                    _sr.to_pitch(source_pitch, flattened.transpose_specs)
                    for source_pitch in chord_pitches
                ]
                event = self._build_voice_event(
                    duration=self.linearizer._duration_from_node(
                        node.duration, flattened.scale
                    ),
                    pitches=pitches,
                    flattened=flattened,
                    pending_directions=state.pending_directions,
                    stem=state.current_stem,
                )
                state.pending_directions.clear()
                if state.pending_glissando_stop and not flattened.is_grace:
                    event.glissando_stop = True
                    state.pending_glissando_stop = False
                self._add_voice_event(
                    voice, state, event, measure_length, source_name, diagnostics, node
                )

            elif isinstance(node, items.Rest):
                state.attachment_event = None
                event = self._build_voice_event(
                    duration=self.linearizer._duration_from_node(
                        node.duration,
                        flattened.scale,
                        token=str(node.token),
                        measure_length=measure_length,
                    ),
                    flattened=flattened,
                    pending_directions=state.pending_directions,
                    is_rest=True,
                )
                state.pending_directions.clear()
                self._add_voice_event(
                    voice, state, event, measure_length, source_name, diagnostics, node
                )

            elif isinstance(node, items.Skip):
                state.attachment_event = None
                event = self._build_voice_event(
                    duration=self.linearizer._duration_from_node(
                        node.duration,
                        flattened.scale,
                        token=str(node.token),
                        measure_length=measure_length,
                    ),
                    flattened=flattened,
                    pending_directions=state.pending_directions,
                    is_rest=True,
                )
                state.pending_directions.clear()
                self._add_voice_event(
                    voice, state, event, measure_length, source_name, diagnostics, node
                )

            elif isinstance(node, _PartialDuration):
                _partial_full_length = measure_length
                measure_length = node.duration

            elif isinstance(node, items.Dynamic):
                direction = self._dynamic_to_direction(str(node.token))
                if direction is None:
                    continue
                self._add_voice_direction(state, direction)

            elif isinstance(node, items.Articulation):
                token = str(node.token)
                coda_segno = CODA_SEGNO_COMMANDS.get(token)
                if coda_segno is not None:
                    self._add_voice_direction(
                        state, Direction(kind=coda_segno, value="")
                    )
                    continue
                target_event = self._voice_attachment_target(state)
                if target_event is None:
                    continue
                articulation = ARTICULATION_MAP.get(token)
                ornament = ORNAMENT_MAP.get(token)
                fermata = FERMATA_MAP.get(token)
                technical = TECHNICAL_MAP.get(token)
                if articulation:
                    target_event.articulations.append(articulation)
                elif ornament:
                    target_event.ornaments.append(ornament)
                elif fermata is not None:
                    target_event.fermatas.append(fermata)
                elif technical:
                    target_event.technical.append(technical)

            elif isinstance(node, items.Slur):
                target_event = self._voice_attachment_target(state)
                if target_event is None:
                    continue
                if node.event == "start":
                    target_event.slur_start_count += 1
                else:
                    target_event.slur_stop_count += 1

            elif isinstance(node, items.PhrasingSlur):
                target_event = self._voice_attachment_target(state)
                if target_event is None:
                    continue
                if node.event == "start":
                    target_event.phrase_slur_start_count += 1
                else:
                    target_event.phrase_slur_stop_count += 1

            elif isinstance(node, items.Tie):
                target_event = self._voice_attachment_target(state)
                if target_event is None:
                    continue
                target_event.tie_start = True
                state.pending_tie_signature = self._voice_event_signature(target_event)

            elif isinstance(node, items.Command):
                token = str(node.token)
                direction = self._dynamic_to_direction(token)
                if direction is not None:
                    self._add_voice_direction(state, direction)
                    continue
                if token in VOICE_COMMAND_STEMS:
                    state.current_stem = VOICE_COMMAND_STEMS[token]
                    continue
                if token in CODA_SEGNO_COMMANDS:
                    self._add_voice_direction(
                        state, Direction(kind=CODA_SEGNO_COMMANDS[token], value="")
                    )
                    continue
                perf_text = PERFORMANCE_TEXT_MARKS.get(token)
                if perf_text is not None:
                    self._add_voice_direction(
                        state, Direction(kind="words", value=perf_text)
                    )
                    continue
                if token == "\\breathe":
                    target_event = self._voice_attachment_target(state)
                    if target_event is not None:
                        target_event.breath_mark = True
                    continue
                if token == "\\arpeggio":
                    target_event = self._voice_attachment_target(state)
                    if target_event is not None:
                        target_event.arpeggiate = True
                    continue
                if token == "\\glissando":
                    target_event = self._voice_attachment_target(state)
                    if target_event is not None:
                        target_event.glissando_start = True
                        state.pending_glissando_stop = True
                    continue
                if token == "\\(":
                    target_event = self._voice_attachment_target(state)
                    if target_event is not None:
                        target_event.phrase_slur_start_count += 1
                    continue
                if token == "\\)":
                    target_event = self._voice_attachment_target(state)
                    if target_event is not None:
                        target_event.phrase_slur_stop_count += 1
                    continue
                if token == "\\compressEmptyMeasures":
                    voice.compress_empty_measures = True
                    continue
                if token in IGNORED_COMMANDS:
                    continue

            elif isinstance(node, items.UserCommand):
                token = str(node.token)
                direction = self._dynamic_to_direction(token)
                if direction is not None:
                    self._add_voice_direction(state, direction)
                else:
                    perf_text = PERFORMANCE_TEXT_MARKS.get(token)
                    if perf_text is not None:
                        self._add_voice_direction(
                            state, Direction(kind="words", value=perf_text)
                        )
                    else:
                        articulation = ARTICULATION_MAP.get(token)
                        ornament = ORNAMENT_MAP.get(token)
                        fermata = FERMATA_MAP.get(token)
                        technical = TECHNICAL_MAP.get(token)
                        if articulation or ornament or fermata is not None or technical:
                            target_event = self._voice_attachment_target(state)
                            if target_event is not None:
                                if articulation:
                                    target_event.articulations.append(articulation)
                                elif ornament:
                                    target_event.ornaments.append(ornament)
                                elif fermata is not None:
                                    target_event.fermatas.append(fermata)
                                elif technical:
                                    target_event.technical.append(technical)

            elif isinstance(node, _SecondaryVoiceBlocks):
                if out_extra_voices is not None:
                    leading_measures = list(voice.measures)
                    partial_elapsed = state.elapsed
                    for secondary_block in node.blocks:
                        sub_voice_id = f"{voice_id}_s{len(out_extra_voices) + 1}"
                        secondary_voice = self.build_voice(
                            voice_id=sub_voice_id,
                            source_name=source_name,
                            music_node=secondary_block,
                            measure_length=measure_length,
                            assignments=assignments,
                            quote_sources=quote_sources,
                            diagnostics=diagnostics,
                            allow_cues=allow_cues,
                            initial_state=node.walk_state,
                            initial_clef=initial_clef,
                            initial_key_fifths=initial_key_fifths,
                            initial_key_mode=initial_key_mode,
                            initial_time_signature=initial_time_signature,
                        )
                        self._prepend_spacer_measures_to_voice(
                            secondary_voice,
                            leading_measures,
                            partial_elapsed,
                        )
                        out_extra_voices.append(secondary_voice)

            elif isinstance(node, items.MusicList) and node.simultaneous:
                diagnostics.append(
                    Diagnostic(
                        code="unsupported-simultaneous-music",
                        message=(
                            f"Voice {source_name} contains simultaneous music "
                            "that is not yet supported."
                        ),
                        severity="error",
                        location=location_from_item(node),
                    )
                )

            elif isinstance(node, items.Repeat):
                diagnostics.append(
                    Diagnostic(
                        code="unsupported-repeat",
                        message=(
                            f"Voice {source_name} contains a repeat that is not "
                            "yet supported."
                        ),
                        severity="error",
                        location=location_from_item(node),
                    )
                )

        if state.current_measure.events or state.elapsed:
            state.current_measure.duration = state.elapsed
            voice.measures.append(state.current_measure)

        return voice

    # ------------------------------------------------------------------
    # Measure lifecycle
    # ------------------------------------------------------------------

    def _finalize_voice_measure(
        self, voice: Voice, state: _VoiceBuildState
    ) -> None:
        state.current_measure.duration = state.elapsed
        voice.measures.append(state.current_measure)
        state.current_measure = Measure(number=state.current_measure.number + 1)
        state.elapsed = Fraction(0, 1)
        state.last_event = None

    def _apply_voice_barline(
        self, voice: Voice, state: _VoiceBuildState, style: str
    ) -> None:
        target_measure = (
            state.current_measure
            if state.current_measure.events or state.elapsed or not voice.measures
            else voice.measures[-1]
        )
        target_measure.right_barline = style

    def _prepend_spacer_measures_to_voice(
        self,
        secondary_voice: Voice,
        leading_measures: list[Measure],
        partial_elapsed: Fraction,
    ) -> None:
        """Align a secondary voice with the primary voice's current position."""

        spacer_measures = [
            Measure(
                number=i + 1,
                events=[MusicEvent(duration=m.duration, is_rest=True)],
                duration=m.duration,
            )
            for i, m in enumerate(leading_measures)
        ]

        if partial_elapsed > 0:
            if secondary_voice.measures:
                first_content = secondary_voice.measures[0]
                leading_rest = MusicEvent(duration=partial_elapsed, is_rest=True)
                first_content.events.insert(0, leading_rest)
                first_content.duration += partial_elapsed
            else:
                spacer_measures.append(
                    Measure(
                        number=len(spacer_measures) + 1,
                        events=[MusicEvent(duration=partial_elapsed, is_rest=True)],
                        duration=partial_elapsed,
                    )
                )

        if not spacer_measures:
            return

        all_measures = spacer_measures + secondary_voice.measures
        for i, measure in enumerate(all_measures):
            measure.number = i + 1
        secondary_voice.measures = all_measures

    # ------------------------------------------------------------------
    # Event building and attachment
    # ------------------------------------------------------------------

    def _build_voice_event(
        self,
        duration: Fraction,
        flattened: _FlattenedNode,
        pending_directions: list[Direction],
        pitches: list[Pitch] | None = None,
        is_rest: bool = False,
        stem: str | None = None,
    ) -> MusicEvent:
        """Construct one intermediate-model event from a flattened parser node."""

        event_kwargs: dict[str, object] = {
            "duration": duration,
            "is_grace": flattened.is_grace,
            "grace_slash": flattened.grace_slash,
            "directions": list(pending_directions),
            "time_modification": flattened.time_modification,
            "tuplet_start": flattened.tuplet_start,
            "tuplet_stop": flattened.tuplet_stop,
            "tremolo_type": flattened.tremolo_type,
            "tremolo_slashes": flattened.tremolo_slashes,
            "stem": stem,
        }
        if pitches is not None:
            event_kwargs["pitches"] = pitches
        if is_rest:
            event_kwargs["is_rest"] = True
        return MusicEvent(**event_kwargs)

    def _clone_event(
        self,
        event: MusicEvent,
        duration: Fraction | None = None,
        is_cue: bool | None = None,
    ) -> MusicEvent:
        return MusicEvent(
            duration=event.duration if duration is None else duration,
            pitches=list(event.pitches),
            is_rest=event.is_rest,
            is_grace=event.is_grace,
            grace_slash=event.grace_slash,
            is_cue=event.is_cue if is_cue is None else is_cue,
            articulations=list(event.articulations),
            ornaments=list(event.ornaments),
            directions=list(event.directions),
            slur_start_count=event.slur_start_count,
            slur_stop_count=event.slur_stop_count,
            tie_start=event.tie_start,
            tie_stop=event.tie_stop,
            time_modification=event.time_modification,
            tuplet_start=event.tuplet_start,
            tuplet_stop=event.tuplet_stop,
            tremolo_type=event.tremolo_type,
            tremolo_slashes=event.tremolo_slashes,
            lyrics=list(event.lyrics),
            arpeggiate=event.arpeggiate,
            glissando_start=event.glissando_start,
            glissando_stop=event.glissando_stop,
            stem=event.stem,
        )

    def _voice_attachment_target(
        self, state: _VoiceBuildState
    ) -> MusicEvent | None:
        return state.last_event or state.attachment_event

    def _voice_event_signature(
        self, event: MusicEvent
    ) -> tuple[tuple[str, int, int], ...] | None:
        if event.is_rest or not event.pitches:
            return None
        return tuple((pitch.step, pitch.alter, pitch.octave) for pitch in event.pitches)

    def _append_voice_rendered_event(
        self,
        state: _VoiceBuildState,
        rendered_event: MusicEvent,
        rendered_duration: Fraction,
        *,
        attach_to_event: bool,
    ) -> None:
        state.current_measure.events.append(rendered_event)
        state.elapsed += rendered_duration
        state.timeline_position += rendered_duration
        state.last_event = rendered_event
        if attach_to_event:
            state.attachment_event = rendered_event

    def _add_voice_event(
        self,
        voice: Voice,
        state: _VoiceBuildState,
        event: MusicEvent,
        measure_length: Fraction,
        source_name: str,
        diagnostics: list[Diagnostic],
        origin: items.Item | None = None,
    ) -> None:
        if (
            state.pending_tie_signature is not None
            and self._voice_event_signature(event) == state.pending_tie_signature
        ):
            event.tie_stop = True
            state.pending_tie_signature = None

        if event.is_grace:
            state.current_measure.events.append(event)
            state.last_event = event
            state.attachment_event = event
            return

        remaining = event.duration
        while remaining > 0:
            available = measure_length - state.elapsed
            if available == 0:
                self._finalize_voice_measure(voice, state)
                available = measure_length

            if not event.is_rest and remaining > available:
                diagnostics.append(
                    Diagnostic(
                        code="measure-overflow",
                        message=(
                            f"Voice {source_name} exceeds the length of measure "
                            f"{state.current_measure.number}."
                        ),
                        severity="error",
                        location=location_from_item(origin) if origin is not None else None,
                    )
                )
                self._append_voice_rendered_event(
                    state,
                    self._clone_event(event, duration=remaining),
                    remaining,
                    attach_to_event=False,
                )
                break

            slice_duration = remaining if remaining <= available else available
            slice_event = self._clone_event(event, duration=slice_duration)
            self._append_voice_rendered_event(
                state, slice_event, slice_duration, attach_to_event=True
            )
            remaining -= slice_duration
            if state.elapsed == measure_length:
                self._finalize_voice_measure(voice, state)

    def _add_voice_direction(
        self, state: _VoiceBuildState, direction: Direction
    ) -> None:
        if state.last_event is not None:
            state.last_event.directions.append(direction)
        else:
            state.pending_directions.append(direction)

    def _add_voice_clef_change(
        self,
        voice: Voice,
        state: _VoiceBuildState,
        node: items.Clef,
        measure_length: Fraction,
        source_name: str,
        diagnostics: list[Diagnostic],
    ) -> None:
        if state.elapsed == measure_length:
            self._finalize_voice_measure(voice, state)

        clef_spec = _sr.resolve_clef(node.specifier())
        if clef_spec is None:
            diagnostics.append(
                Diagnostic(
                    code="unsupported-clef",
                    message=f"Unsupported clef in voice {source_name}: {node.specifier()}",
                    severity="warning",
                    location=location_from_item(node),
                )
            )
            return

        if clef_spec == state.current_clef:
            return

        clef_change = ClefChange(
            offset=state.elapsed,
            sign=clef_spec[0],
            line=clef_spec[1],
            octave_change=clef_spec[2],
        )
        if (
            state.current_measure.clef_changes
            and state.current_measure.clef_changes[-1].offset == clef_change.offset
        ):
            state.current_measure.clef_changes[-1] = clef_change
        else:
            state.current_measure.clef_changes.append(clef_change)
        state.current_clef = clef_spec

    # ------------------------------------------------------------------
    # Cue expansion
    # ------------------------------------------------------------------

    def _add_cue_insertion(
        self,
        voice: Voice,
        state: _VoiceBuildState,
        cue: _CueInsertion,
        measure_length: Fraction,
        source_name: str,
        assignments: Mapping[str, items.Item],
        quote_sources: Mapping[str, items.Item],
        diagnostics: list[Diagnostic],
    ) -> None:
        state.attachment_event = None
        if cue.duration <= 0:
            return
        if cue.suppressed:
            self._add_voice_event(
                voice,
                state,
                MusicEvent(duration=cue.duration, is_rest=True),
                measure_length,
                source_name,
                diagnostics,
                cue.source_node,
            )
            return
        cue_events = self._expand_cue_insertion(
            cue,
            state.timeline_position,
            measure_length,
            assignments,
            quote_sources,
            diagnostics,
        )
        rendered_duration = Fraction(0, 1)
        for cue_event in cue_events:
            self._add_voice_event(
                voice,
                state,
                cue_event,
                measure_length,
                source_name,
                diagnostics,
                cue.source_node,
            )
            if not cue_event.is_grace:
                rendered_duration += cue_event.duration
        if rendered_duration < cue.duration:
            self._add_voice_event(
                voice,
                state,
                MusicEvent(duration=cue.duration - rendered_duration, is_rest=True),
                measure_length,
                source_name,
                diagnostics,
                cue.source_node,
            )

    def _expand_cue_insertion(
        self,
        cue: _CueInsertion,
        start_offset: Fraction,
        measure_length: Fraction,
        assignments: dict[str, items.Item | None],
        quote_sources: dict[str, items.Item],
        diagnostics: list[Diagnostic],
    ) -> list[MusicEvent]:
        """Resolve one cue request into the slice of quote events it should emit."""

        quote_voice = self._quote_voice(
            cue.quote_name, measure_length, assignments, quote_sources, diagnostics
        )
        if quote_voice is None:
            diagnostics.append(
                Diagnostic(
                    code="missing-cue-quote",
                    message=f'Cue quote "{cue.quote_name}" is not defined.',
                    severity="warning",
                    location=location_from_item(cue.source_node),
                )
            )
            return []
        return self._slice_voice_events(quote_voice, start_offset, cue.duration)

    def _quote_voice(
        self,
        quote_name: str,
        measure_length: Fraction,
        assignments: dict[str, items.Item | None],
        quote_sources: dict[str, items.Item],
        diagnostics: list[Diagnostic],
    ) -> Voice | None:
        quote_source = quote_sources.get(quote_name)
        if quote_source is None:
            return None

        cache_key = (quote_name, measure_length)
        cached_voice = self._quote_voice_cache.get(cache_key)
        if cached_voice is not None:
            return cached_voice

        quote_voice = self.build_voice(
            voice_id=f"quote:{quote_name}",
            source_name=quote_name,
            music_node=quote_source,
            measure_length=measure_length,
            assignments=assignments,
            quote_sources=quote_sources,
            diagnostics=diagnostics,
            allow_cues=False,
        )
        self._quote_voice_cache[cache_key] = quote_voice
        return quote_voice

    def _slice_voice_events(
        self, voice: Voice, start_offset: Fraction, duration: Fraction
    ) -> list[MusicEvent]:
        events: list[MusicEvent] = []
        cursor = Fraction(0, 1)
        end_offset = start_offset + duration

        for measure in voice.measures:
            for event in measure.events:
                if event.is_grace:
                    continue
                next_cursor = cursor + event.duration
                if next_cursor <= start_offset:
                    cursor = next_cursor
                    continue
                if cursor >= end_offset:
                    return events
                overlap_start = max(cursor, start_offset)
                overlap_end = min(next_cursor, end_offset)
                if overlap_end > overlap_start:
                    events.append(
                        self._clone_event(
                            event,
                            duration=overlap_end - overlap_start,
                            is_cue=True,
                        )
                    )
                cursor = next_cursor
                if cursor >= end_offset:
                    return events

        return events

    # ------------------------------------------------------------------
    # Lyric attachment
    # ------------------------------------------------------------------

    def _iter_lyric_tokens(
        self,
        node: items.Item,
        assignments: dict[str, items.Item | None],
        state: _WalkState | None = None,
    ) -> Iterable[_LyricToken]:
        state = state or _WalkState()
        if isinstance(node, items.UserCommand):
            value = node.value()
            if not isinstance(value, items.Item):
                value = assignments.get(node.name())
            if isinstance(value, items.Item):
                yield from self._iter_lyric_tokens(value, assignments, state)
            return

        if isinstance(node, items.Tag):
            tag_result = self.linearizer._consume_tag_filter([node], 0, state)
            if tag_result is not None:
                for child, child_state in tag_result.emitted:
                    yield from self._iter_lyric_tokens(
                        child, assignments, child_state
                    )
                return

        if isinstance(node, (items.LyricMode, items.LyricsTo, items.MusicList)):
            for child, child_state in self.linearizer._iter_filtered_children(
                node, state
            ):
                yield from self._iter_lyric_tokens(child, assignments, child_state)
            return

        if isinstance(node, items.LyricText):
            text = str(node.token).strip()
            if text:
                yield _LyricToken(kind="text", text=text)
            return

        if isinstance(node, items.LyricItem):
            token = str(node.token)
            if token == "--":
                yield _LyricToken(kind="hyphen")
            elif token == "__":
                yield _LyricToken(kind="extend")
            elif token == "_":
                yield _LyricToken(kind="skip")
            return

    def _apply_lyrics(
        self,
        voice: Voice,
        lyric_source: items.Item,
        assignments: dict[str, items.Item | None],
        initial_state: _WalkState | None = None,
        verse_number: int | None = None,
        diagnostics: list[Diagnostic] | None = None,
    ) -> None:
        """Attach lyric tokens to note events in score order for one voice."""

        note_events = [
            event
            for measure in voice.measures
            for event in measure.events
            if event.is_note and not event.is_grace
        ]
        if not note_events:
            return

        lyric_tokens = list(
            self._iter_lyric_tokens(
                lyric_source, assignments, initial_state or _WalkState()
            )
        )
        note_index = 0
        previous_hyphen = False
        last_lyric_event: MusicEvent | None = None
        surplus_tokens: list[_LyricToken] = []

        for index, token in enumerate(lyric_tokens):
            if note_index >= len(note_events):
                surplus_tokens = lyric_tokens[index:]
                break

            if token.kind == "text":
                next_kind = (
                    lyric_tokens[index + 1].kind
                    if index + 1 < len(lyric_tokens)
                    else None
                )
                if previous_hyphen and next_kind == "hyphen":
                    syllabic = "middle"
                elif previous_hyphen:
                    syllabic = "end"
                elif next_kind == "hyphen":
                    syllabic = "begin"
                else:
                    syllabic = "single"

                note_event = note_events[note_index]
                note_event.lyrics.append(
                    Lyric(
                        text=token.text or "",
                        syllabic=syllabic,
                        number=verse_number,
                    )
                )
                last_lyric_event = note_event
                note_index += 1
                previous_hyphen = False
            elif token.kind == "hyphen":
                previous_hyphen = True
            elif token.kind == "extend":
                if last_lyric_event is not None and last_lyric_event.lyrics:
                    current_lyric = last_lyric_event.lyrics[-1]
                    last_lyric_event.lyrics[-1] = Lyric(
                        text=current_lyric.text,
                        syllabic=current_lyric.syllabic,
                        extend=True,
                        number=current_lyric.number,
                    )
                note_index += 1
                previous_hyphen = False
            elif token.kind == "skip":
                note_index += 1
                previous_hyphen = False

        if diagnostics is not None:
            surplus_syllables = sum(
                1 for t in surplus_tokens if t.kind == "text"
            )
            if surplus_syllables:
                verse_label = (
                    f" (verse {verse_number})" if verse_number is not None else ""
                )
                diagnostics.append(
                    Diagnostic(
                        code="lyric-surplus",
                        message=(
                            f"Voice {voice.source_name} has {surplus_syllables}"
                            f" lyric syllable(s) with no matching note{verse_label}."
                        ),
                        severity="warning",
                    )
                )

    # ------------------------------------------------------------------
    # Direction helpers
    # ------------------------------------------------------------------

    def _dynamic_to_direction(self, token: str) -> Direction | None:
        dynamic = DYNAMIC_MARKS.get(token)
        if dynamic:
            return Direction(kind="dynamic", value=dynamic)
        wedge = WEDGE_DYNAMICS.get(token)
        if wedge:
            return Direction(kind="wedge", value=wedge)
        text = TEXT_DYNAMICS.get(token)
        if text:
            return Direction(kind="words", value=text)
        return None

    def _ottava_directions(
        self, ottava_value: int, active_ottava: int | None
    ) -> list[Direction]:
        directions: list[Direction] = []
        if active_ottava is not None and active_ottava != ottava_value:
            directions.append(self._ottava_direction(active_ottava, "stop"))
        if ottava_value != 0 and ottava_value != active_ottava:
            shift_type = "up" if ottava_value < 0 else "down"
            directions.append(self._ottava_direction(ottava_value, shift_type))
        return directions

    def _ottava_direction(self, ottava_value: int, shift_type: str) -> Direction:
        placement = "below" if ottava_value < 0 else "above"
        size = abs(ottava_value) * 7 + 1
        return Direction(
            kind="octave-shift", value=f"{placement}:{shift_type}:{size}"
        )

    def _tempo_directions(self, node: items.Tempo) -> list[Direction]:
        """Return Direction objects representing one LilyPond tempo mark."""

        directions: list[Direction] = []
        text = self.linearizer._extract_text(node.text())
        if text:
            directions.append(Direction(kind="tempo", value=text))

        duration_attr = getattr(node, "duration", None)
        if duration_attr and duration_attr[0]:
            beat_fraction = duration_attr[0] * duration_attr[1]
            beat_unit = _sr.BEAT_UNIT_MAP.get(beat_fraction)
            bpm = next(
                (
                    int(str(child.token))
                    for child in node
                    if isinstance(child, items.Number)
                    and str(child.token).isdigit()
                ),
                None,
            )
            if beat_unit and bpm is not None:
                directions.append(
                    Direction(kind="metronome", value=f"{beat_unit}:{bpm}")
                )

        return directions

    # ------------------------------------------------------------------
    # Clef helpers
    # ------------------------------------------------------------------

    def _barline_style(self, value: str) -> str | None:
        return {
            "||": "light-light",
            "|.": "light-heavy",
            ".|": "heavy-light:forward",
            ".|.": "heavy-heavy",
            ":.": "dotted",
            "!": "short",
            "'": "tick",
            "-": "dashed",
            "": "none",
            ";": "tick",
            "\\|:": "heavy-light:forward",
            ":|": "light-heavy:backward",
            ":|:": "light-heavy:backward",
            "|:": "heavy-light:forward",
            "::": "dotted",
        }.get(value)
