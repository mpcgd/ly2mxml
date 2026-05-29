from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction
from math import lcm
from pathlib import Path
import re
from typing import Iterable, Iterator

from ly.music import items

from ly2mxml.diagnostics import Diagnostic, location_from_item
from ly2mxml.frontend.python_ly_adapter import PythonLyAdapter, SourceAnalysis
from ly2mxml.model.score import Direction, Lyric, Measure, MusicEvent, Part, PartCombineMode, Pitch, Score, ScoreMetadata, Voice
from ly2mxml.musicxml.writer import MusicXmlWriter
from ly2mxml.options import ExportOptions


KNOWN_BUILTIN_USER_COMMANDS = {
    "addQuote",
    "compressEmptyMeasures",
    "killCues",
    "ottava",
    "partCombine",
    "removeWithTag",
    "tag",
}

SUPPORTED_FEATURES = {
    "barlines",
    "cue-filtering",
    "cue-quotes",
    "grace-notes",
    "lyrics",
    "multi-measure-rests",
    "part-combine",
    "relative-pitch",
    "repeat:unfold",
    "repeat:volta",
    "scaled-durations",
    "scheme",
    "tag-filtering",
    "transpose",
    "user-variables",
}

UNSUPPORTED_FEATURE_MESSAGES = {}

IGNORED_COMMANDS = {
    "\\compressEmptyMeasures",
}

DYNAMIC_MARKS = {
    "\\pp": "pp",
    "\\p": "p",
    "\\mp": "mp",
    "\\mf": "mf",
    "\\f": "f",
    "\\ff": "ff",
    "\\fff": "fff",
    "\\sf": "sf",
    "\\sfp": "sfp",
}

TEXT_DYNAMICS = {
    "\\cresc": "cresc.",
    "\\dim": "dim.",
    "\\decresc": "decresc.",
}

WEDGE_DYNAMICS = {
    "\\<": "crescendo",
    "\\>": "diminuendo",
    "\\!": "stop",
}

ARTICULATION_MAP = {
    "-.": "staccato",
    ".": "staccato",
    "->": "accent",
    ">": "accent",
    "--": "tenuto",
    "-^": "strong-accent",
    "^": "strong-accent",
}

ORNAMENT_MAP = {
    "\\trill": "trill-mark",
}

CLEF_MAP = {
    "treble": ("G", 2),
    "alto": ("C", 3),
    "bass": ("F", 4),
}

STEP_MAP = {
    0: "C",
    1: "D",
    2: "E",
    3: "F",
    4: "G",
    5: "A",
    6: "B",
}

KEY_FIFTHS = {
    (0, 0, "major"): 0,
    (4, 0, "major"): 1,
    (1, 0, "major"): 2,
    (5, 0, "major"): 3,
    (2, 0, "major"): 4,
    (6, 0, "major"): 5,
    (3, 1, "major"): 6,
    (0, 1, "major"): 7,
    (3, 0, "major"): -1,
    (6, -1, "major"): -2,
    (2, -1, "major"): -3,
    (5, -1, "major"): -4,
    (1, -1, "major"): -5,
    (4, -1, "major"): -6,
    (0, -1, "major"): -7,
    (5, 0, "minor"): 0,
    (2, 0, "minor"): 1,
    (6, 0, "minor"): 2,
    (3, 1, "minor"): 3,
    (0, 1, "minor"): 4,
    (4, 1, "minor"): 5,
    (1, 1, "minor"): 6,
    (5, 1, "minor"): 7,
    (1, 0, "minor"): -1,
    (4, 0, "minor"): -2,
    (0, 0, "minor"): -3,
    (3, 0, "minor"): -4,
    (6, -1, "minor"): -5,
    (2, -1, "minor"): -6,
    (5, -1, "minor"): -7,
}

PITCH_SCALE = (Fraction(0, 1), Fraction(2, 1), Fraction(4, 1), Fraction(5, 1), Fraction(7, 1), Fraction(9, 1), Fraction(11, 1))

DEFINE_PUBLIC_STRING_PATTERN = re.compile(r'#\(define-public\s+([\w-]+)\s+"([^"]*)"\)')
NEW_CONTEXT_PATTERN = re.compile(r'\\new\s+([A-Za-z]+)(?:\s*=\s*"([^"]+)")?\s*$')
UNRESOLVED_COMMAND_PATTERN = re.compile(r"\\+([A-Za-z]+)\b")
MUSICAL_NODE_TYPES = (items.Note, items.Rest, items.Chord)


@dataclass(slots=True)
class ConversionPreflight:
    analysis: SourceAnalysis
    diagnostics: list[Diagnostic] = field(default_factory=list)
    supported_features: set[str] = field(default_factory=set)
    unsupported_features: set[str] = field(default_factory=set)

    @property
    def has_errors(self) -> bool:
        return any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


@dataclass(slots=True)
class ConversionResult:
    preflight: ConversionPreflight
    score: Score | None = None
    output_path: Path | None = None


@dataclass(slots=True)
class _GlobalSettings:
    time_signature: tuple[int, int] = (4, 4)
    key_fifths: int = 0
    key_mode: str = "major"
    tempo_text: str | None = None


@dataclass(frozen=True, slots=True)
class _WalkState:
    is_grace: bool = False
    grace_slash: bool = False
    scale: Fraction = Fraction(1, 1)
    cues_killed: bool = False
    allow_cues: bool = True
    removed_tags: frozenset[str] = frozenset()
    transpose_specs: tuple["_TransposeSpec", ...] = ()
    relative_reference: object | None = None
    measure_length: Fraction | None = None


@dataclass(frozen=True, slots=True)
class _SequenceFilterResult:
    emitted: tuple[tuple[items.Item, _WalkState], ...]
    remaining_state: _WalkState
    consumed: int


@dataclass(frozen=True, slots=True)
class _TransposeSpec:
    octave: int
    steps: int
    alter: Fraction


@dataclass(frozen=True, slots=True)
class _VoiceReference:
    name: str
    state: _WalkState
    context_id: str | None = None
    music_node: items.Item | None = None

    @property
    def lyric_target(self) -> str:
        return self.context_id or self.name


@dataclass(frozen=True, slots=True)
class _CueInsertion:
    quote_name: str
    duration: Fraction
    source_node: items.Item
    suppressed: bool


@dataclass(frozen=True, slots=True)
class _OttavaChange:
    value: int
    source_node: items.Item


@dataclass(frozen=True, slots=True)
class _BarlineChange:
    value: str
    source_node: items.Item


@dataclass(frozen=True, slots=True)
class _NewContextCommand:
    context_type: str
    context_id: str | None
    content_node: items.Item
    consumed: int


@dataclass(slots=True)
class _FlattenedNode:
    node: items.Item | _CueInsertion | _OttavaChange | _BarlineChange
    is_grace: bool
    grace_slash: bool
    scale: Fraction
    transpose_specs: tuple[_TransposeSpec, ...] = ()
    time_modification: tuple[int, int] | None = None
    tuplet_start: bool = False
    tuplet_stop: bool = False
    resolved_pitches: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class _LyricToken:
    kind: str
    text: str | None = None


@dataclass(frozen=True, slots=True)
class _PartCombinePlan:
    voice_refs: tuple[_VoiceReference, ...]
    names: tuple[str, ...]
    short_names: tuple[str | None, ...]
    group_id: str


class LilypondConverter:
    def __init__(
        self,
        adapter: PythonLyAdapter | None = None,
        writer: MusicXmlWriter | None = None,
        partcombine_mode: PartCombineMode = "separate",
        export_options: ExportOptions | None = None,
    ) -> None:
        self.adapter = adapter or PythonLyAdapter()
        self.writer = writer or MusicXmlWriter()
        if export_options is None:
            export_options = ExportOptions(partcombine_mode=partcombine_mode)
        elif partcombine_mode != "separate" and export_options.partcombine_mode != partcombine_mode:
            export_options = ExportOptions(partcombine_mode=partcombine_mode, cue_mode=export_options.cue_mode)

        self.export_options = export_options
        self.partcombine_mode = export_options.partcombine_mode
        self._source_text_cache: dict[Path, str] = {}
        self._quote_voice_cache: dict[tuple[str, Fraction], Voice] = {}

    def preflight(self, entrypoint: str | Path) -> ConversionPreflight:
        analysis = self.adapter.inspect(entrypoint)
        scheme_values = self._collect_define_public_strings(self.adapter.load_document_tree(entrypoint))
        diagnostics: list[Diagnostic] = []
        supported_features: set[str] = set()
        unsupported_features: set[str] = set()

        for diagnostic in analysis.diagnostics:
            if diagnostic.code == "unresolved-user-command":
                name = diagnostic.message.rsplit("\\", 1)[-1]
                if name in KNOWN_BUILTIN_USER_COMMANDS or name in scheme_values:
                    continue
            diagnostics.append(diagnostic)

        for feature in analysis.features:
            if feature in SUPPORTED_FEATURES:
                supported_features.add(feature)
                continue
            if feature.startswith("repeat:"):
                unsupported_features.add(feature)
                diagnostics.append(
                    Diagnostic(
                        code="unsupported-feature",
                        message=f"Repeat handling is not implemented yet: {feature}",
                        severity="error",
                        location=None if not analysis.diagnostics else analysis.diagnostics[0].location,
                    )
                )
                continue
            message = UNSUPPORTED_FEATURE_MESSAGES.get(feature)
            if message:
                unsupported_features.add(feature)
                diagnostics.append(
                    Diagnostic(
                        code="unsupported-feature",
                        message=message,
                        severity="error",
                        location=None if not analysis.diagnostics else analysis.diagnostics[0].location,
                    )
                )
            else:
                supported_features.add(feature)

        return ConversionPreflight(
            analysis=analysis,
            diagnostics=diagnostics,
            supported_features=supported_features,
            unsupported_features=unsupported_features,
        )

    def build_score(self, entrypoint: str | Path) -> Score:
        document = self.adapter.load_document_tree(entrypoint)
        assignments = self._collect_assignments(document)
        quote_sources = self._collect_quotes(document, assignments)
        scheme_values = self._collect_define_public_strings(document)
        metadata = self._extract_metadata(document, scheme_values)
        score_node = self._first_score(document)
        diagnostics: list[Diagnostic] = []
        self._quote_voice_cache = {}

        if score_node is None:
            diagnostics.append(
                Diagnostic(
                    code="missing-score",
                    message="No LilyPond score block was found.",
                    severity="error",
                )
            )
            return Score(metadata=metadata, diagnostics=diagnostics)

        parts: list[Part] = []
        next_part_index = 1
        for staff_index, (staff_context, walk_state) in enumerate(self._iter_staff_contexts(score_node), start=1):
            built_parts = self._build_parts(
                staff_context,
                staff_index,
                next_part_index,
                assignments,
                quote_sources,
                diagnostics,
                walk_state,
            )
            for part in built_parts:
                if part.voices:
                    part.divisions = self._compute_divisions(part)
                    parts.append(part)
            next_part_index += len(built_parts)

        return Score(metadata=metadata, parts=parts, diagnostics=diagnostics)

    def convert_file(self, entrypoint: str | Path, output_path: str | Path) -> ConversionResult:
        preflight = self.preflight(entrypoint)
        if preflight.has_errors:
            return ConversionResult(preflight=preflight)

        score = self.build_score(entrypoint)
        result = ConversionResult(preflight=preflight, score=score)
        if any(diagnostic.severity == "error" for diagnostic in score.diagnostics):
            return result

        resolved_output = self.writer.write(score, output_path, export_options=self.export_options)
        result.output_path = resolved_output
        return result

    def _collect_assignments(self, document: items.Document) -> dict[str, items.Item | None]:
        assignments: dict[str, items.Item | None] = {}
        visited_paths: set[Path] = set()

        def visit(doc: items.Document) -> None:
            raw_file_name = getattr(doc.document, "filename", None)
            resolved_file_name = Path(raw_file_name).resolve() if raw_file_name else None
            if resolved_file_name in visited_paths:
                return
            if resolved_file_name is not None:
                visited_paths.add(resolved_file_name)

            for node in doc:
                if isinstance(node, items.Assignment):
                    assignments[str(node.name())] = node.value()
                elif isinstance(node, items.Include):
                    included = doc.get_included_document_node(node)
                    if included is not None:
                        visit(included)

        visit(document)
        return assignments

    def _extract_metadata(self, document: items.Document, scheme_values: dict[str, str]) -> ScoreMetadata:
        metadata = ScoreMetadata()
        header = next((node for node in document if isinstance(node, items.Header)), None)
        if header is None:
            return metadata

        for node in header:
            if not isinstance(node, items.Assignment):
                continue
            name = str(node.name())
            value = self._extract_text(node.value(), scheme_values)
            if name == "title":
                metadata.title = value
            elif name == "composer":
                metadata.composer = value
            elif name == "arranger":
                metadata.arranger = value
        return metadata

    def _collect_quotes(
        self,
        document: items.Document,
        assignments: dict[str, items.Item | None],
    ) -> dict[str, items.Item]:
        quotes: dict[str, items.Item] = {}
        visited_paths: set[Path] = set()

        def visit(doc: items.Document) -> None:
            raw_file_name = getattr(doc.document, "filename", None)
            resolved_file_name = Path(raw_file_name).resolve() if raw_file_name else None
            if resolved_file_name in visited_paths:
                return
            if resolved_file_name is not None:
                visited_paths.add(resolved_file_name)

            sequence = [node for node in doc if isinstance(node, items.Item)]
            index = 0
            while index < len(sequence):
                node = sequence[index]
                if isinstance(node, items.Command) and str(node.token) == "\\addQuote":
                    quote_name_node = sequence[index + 1] if index + 1 < len(sequence) else None
                    quote_source_node = sequence[index + 2] if index + 2 < len(sequence) else None
                    quote_name = self._extract_text(quote_name_node)
                    quote_source = self._resolve_item_reference(quote_source_node, assignments)
                    if quote_name and isinstance(quote_source, items.Item):
                        quotes[quote_name] = quote_source
                    index += 3
                    continue

                if isinstance(node, items.Include):
                    included = doc.get_included_document_node(node)
                    if included is not None:
                        visit(included)
                index += 1

        visit(document)
        return quotes

    def _collect_define_public_strings(self, document: items.Document) -> dict[str, str]:
        values: dict[str, str] = {}
        visited_paths: set[Path] = set()

        def visit(doc: items.Document) -> None:
            raw_file_name = getattr(doc.document, "filename", None)
            resolved_file_name = Path(raw_file_name).resolve() if raw_file_name else None
            if resolved_file_name in visited_paths:
                return
            if resolved_file_name is not None:
                visited_paths.add(resolved_file_name)
                source_text = self.adapter.loader.read_text(resolved_file_name)
                for name, value in DEFINE_PUBLIC_STRING_PATTERN.findall(source_text):
                    values[name] = value

            for node in doc:
                if isinstance(node, items.Include):
                    included = doc.get_included_document_node(node)
                    if included is not None:
                        visit(included)

        visit(document)
        return values

    def _first_score(self, document: items.Document) -> items.Score | None:
        for node in document:
            if isinstance(node, items.Score):
                return node
        return None

    def _iter_staff_contexts(self, node: items.Item, state: _WalkState | None = None) -> Iterator[tuple[items.Context, _WalkState]]:
        state = state or _WalkState()
        if isinstance(node, items.Context) and node.context() == "Staff":
            yield node, state
            return
        for child, child_state in self._iter_filtered_children(node, state):
            yield from self._iter_staff_contexts(child, child_state)

    def _build_parts(
        self,
        staff_context: items.Context,
        staff_index: int,
        start_part_index: int,
        assignments: dict[str, items.Item | None],
        quote_sources: dict[str, items.Item],
        diagnostics: list[Diagnostic],
        initial_state: _WalkState,
    ) -> list[Part]:
        with_node = next((child for child in staff_context if isinstance(child, items.With)), None)
        music_node = next((child for child in staff_context if isinstance(child, items.Music)), None)

        name, short_name = self._extract_part_names(with_node)
        clef_name = "treble"
        global_ref = _VoiceReference("global", initial_state)
        voice_refs: list[_VoiceReference] = []
        partcombine_groups: list[_PartCombinePlan] = []
        lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]] = {}
        last_voice_ref: _VoiceReference | None = None
        container_end_position = music_node.end_position() if music_node is not None and callable(getattr(music_node, "end_position", None)) else None

        if isinstance(music_node, items.MusicList):
            sequence = list(self._iter_filtered_children(music_node, initial_state))
        elif isinstance(music_node, items.Item):
            sequence = [(music_node, initial_state)]
        else:
            sequence = []

        position = 0
        while position < len(sequence):
            node, node_state = sequence[position]
            if isinstance(node, items.Context):
                context_name = node.context()
                if context_name == "Voice":
                    voice_child = next((child for child in node if isinstance(child, items.Item)), None)
                    if voice_child is not None:
                        voice_ref = self._voice_reference_from_node(
                            voice_child,
                            node_state,
                            assignments,
                            sequence[position + 1][0] if position + 1 < len(sequence) else None,
                            container_end_position,
                            staff_index,
                            len(voice_refs) + sum(len(group.voice_refs) for group in partcombine_groups) + 1,
                            node.context_id(),
                        )
                        if voice_ref is not None:
                            voice_refs.append(voice_ref)
                            last_voice_ref = voice_ref
                    position += 1
                    continue
                if context_name == "Lyrics":
                    lyric_child = next((child for child in node if isinstance(child, items.Item)), None)
                    if lyric_child is not None:
                        lyric_reference = self._resolve_item_reference(
                            lyric_child,
                            assignments,
                            sequence[position + 1][0] if position + 1 < len(sequence) else None,
                            container_end_position,
                        )
                        if isinstance(lyric_reference, items.LyricsTo):
                            target = lyric_reference.context_id()
                            if target:
                                lyric_sources.setdefault(target, []).append((lyric_reference, node_state))
                    position += 1
                    continue

            new_context = self._parse_new_context(sequence, position, container_end_position)
            if new_context is not None:
                if new_context.context_type == "Voice":
                    voice_ref = self._resolve_voice_reference(
                        new_context,
                        node_state,
                        assignments,
                        sequence,
                        position,
                        container_end_position,
                        staff_index,
                        len(voice_refs) + sum(len(group.voice_refs) for group in partcombine_groups) + 1,
                    )
                    if voice_ref is not None:
                        voice_refs.append(voice_ref)
                        last_voice_ref = voice_ref
                elif new_context.context_type == "Lyrics":
                    next_node = sequence[position + new_context.consumed][0] if position + new_context.consumed < len(sequence) else None
                    lyric_reference = self._resolve_item_reference(
                        new_context.content_node,
                        assignments,
                        next_node,
                        container_end_position,
                    )
                    if isinstance(lyric_reference, items.LyricsTo):
                        target = lyric_reference.context_id()
                        if target:
                            lyric_sources.setdefault(target, []).append((lyric_reference, node_state))
                position += new_context.consumed
                continue

            if isinstance(node, items.Clef):
                clef_name = node.specifier() or clef_name
            elif isinstance(node, items.Command) and str(node.token) == "\\partCombine":
                left = sequence[position + 1] if position + 1 < len(sequence) else None
                right = sequence[position + 2] if position + 2 < len(sequence) else None
                planned_voice_refs: list[_VoiceReference] = []
                if left is not None:
                    left_ref = self._voice_reference_from_node(
                        left[0],
                        left[1],
                        assignments,
                        sequence[position + 3][0] if position + 3 < len(sequence) else None,
                        container_end_position,
                        staff_index,
                        len(voice_refs) + len(planned_voice_refs) + 1,
                    )
                    if left_ref is not None:
                        planned_voice_refs.append(left_ref)
                        last_voice_ref = left_ref
                if right is not None:
                    right_ref = self._voice_reference_from_node(
                        right[0],
                        right[1],
                        assignments,
                        sequence[position + 4][0] if position + 4 < len(sequence) else None,
                        container_end_position,
                        staff_index,
                        len(voice_refs) + len(planned_voice_refs) + 1,
                    )
                    if right_ref is not None:
                        planned_voice_refs.append(right_ref)
                        last_voice_ref = right_ref
                if len(planned_voice_refs) == 2:
                    inferred_names, inferred_short_names = self._infer_partcombine_labels(
                        name,
                        short_name,
                        [voice_ref.name for voice_ref in planned_voice_refs],
                    )
                    partcombine_groups.append(
                        _PartCombinePlan(
                            voice_refs=tuple(planned_voice_refs),
                            names=tuple(inferred_names),
                            short_names=tuple(inferred_short_names),
                            group_id=f"staff-{staff_index}-combine-{len(partcombine_groups) + 1}",
                        )
                    )
                else:
                    voice_refs.extend(planned_voice_refs)
                position += 2
            elif isinstance(node, items.UserCommand):
                command_name = node.name()
                if command_name in {"global", "globalNoKey"}:
                    global_ref = _VoiceReference(command_name, node_state)
                elif command_name not in KNOWN_BUILTIN_USER_COMMANDS:
                    voice_ref = _VoiceReference(command_name, node_state)
                    voice_refs.append(voice_ref)
                    last_voice_ref = voice_ref
            elif isinstance(node, items.VoiceSeparator):
                next_node = sequence[position + 1][0] if position + 1 < len(sequence) else None
                command_name = self._raw_command_name_until(
                    node,
                    getattr(next_node, "position", None) if next_node is not None else container_end_position,
                )
                if command_name in {"global", "globalNoKey"}:
                    global_ref = _VoiceReference(command_name, node_state)
                elif command_name and command_name not in KNOWN_BUILTIN_USER_COMMANDS:
                    voice_ref = _VoiceReference(command_name, node_state)
                    voice_refs.append(voice_ref)
                    last_voice_ref = voice_ref
            elif isinstance(node, items.LyricMode) and str(node.token) == "\\addlyrics" and last_voice_ref is not None:
                lyric_sources.setdefault(last_voice_ref.lyric_target, []).append((node, last_voice_ref.state))
            position += 1

        global_settings = self._parse_global_settings(assignments.get(global_ref.name), diagnostics, global_ref.name, global_ref.state)
        clef_sign, clef_line = CLEF_MAP.get(clef_name, ("G", 2))
        built_parts: list[Part] = []
        next_part_index = start_part_index

        if partcombine_groups:
            for group in partcombine_groups:
                for member_index, voice_ref in enumerate(group.voice_refs, start=1):
                    part = Part(
                        id=f"P{next_part_index}",
                        name=group.names[member_index - 1],
                        short_name=group.short_names[member_index - 1],
                        clef_sign=clef_sign,
                        clef_line=clef_line,
                        time_signature=global_settings.time_signature,
                        key_fifths=global_settings.key_fifths,
                        key_mode=global_settings.key_mode,
                        tempo_text=global_settings.tempo_text,
                        combine_group=group.group_id,
                        combine_member=member_index,
                        combined_name=name or f"Part {staff_index}",
                        combined_short_name=short_name,
                    )
                    self._append_part_voice(
                        part,
                        voice_ref,
                        "1",
                        assignments,
                        quote_sources,
                        diagnostics,
                        lyric_sources,
                    )
                    built_parts.append(part)
                    next_part_index += 1

        if voice_refs:
            part = Part(
                id=f"P{next_part_index}",
                name=name or f"Part {staff_index}",
                short_name=short_name,
                clef_sign=clef_sign,
                clef_line=clef_line,
                time_signature=global_settings.time_signature,
                key_fifths=global_settings.key_fifths,
                key_mode=global_settings.key_mode,
                tempo_text=global_settings.tempo_text,
            )
            for voice_index, voice_ref in enumerate(voice_refs, start=1):
                self._append_part_voice(
                    part,
                    voice_ref,
                    str(voice_index),
                    assignments,
                    quote_sources,
                    diagnostics,
                    lyric_sources,
                )
            built_parts.append(part)

        return built_parts

    def _append_part_voice(
        self,
        part: Part,
        voice_ref: _VoiceReference,
        voice_id: str,
        assignments: dict[str, items.Item | None],
        quote_sources: dict[str, items.Item],
        diagnostics: list[Diagnostic],
        lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]],
    ) -> None:
        voice_music = voice_ref.music_node or assignments.get(voice_ref.name)
        if not isinstance(voice_music, items.Item):
            diagnostics.append(
                Diagnostic(
                    code="missing-voice",
                    message=f"Unable to resolve voice assignment: {voice_ref.name}",
                    severity="error",
                )
            )
            return

        voice = self._build_voice(
            voice_id=voice_id,
            source_name=voice_ref.name,
            music_node=voice_music,
            measure_length=part.measure_length,
            assignments=assignments,
            quote_sources=quote_sources,
            diagnostics=diagnostics,
            initial_state=voice_ref.state,
        )
        target_lyrics = lyric_sources.get(voice_ref.lyric_target, [])
        for verse_index, (lyric_source, lyric_state) in enumerate(target_lyrics, start=1):
            verse_number = verse_index if len(target_lyrics) > 1 else None
            self._apply_lyrics(voice, lyric_source, assignments, lyric_state, verse_number)
        part.voices.append(voice)

    def _infer_partcombine_labels(
        self,
        combined_name: str | None,
        combined_short_name: str | None,
        voice_names: list[str],
    ) -> tuple[list[str], list[str | None]]:
        base_name = self._normalize_partcombine_label(combined_name) or self._humanize_voice_name(voice_names[0])
        base_short_name = self._normalize_short_partcombine_label(combined_short_name)
        names: list[str] = []
        short_names: list[str | None] = []
        for member_index, voice_name in enumerate(voice_names, start=1):
            suffix = self._partcombine_suffix(voice_name, member_index)
            names.append(f"{base_name} {suffix}")
            short_names.append(f"{base_short_name} {suffix}" if base_short_name else None)
        return names, short_names

    def _normalize_partcombine_label(self, label: str | None) -> str | None:
        if label is None:
            return None
        normalized = re.sub(r"\s*\([^)]*\)", "", label).strip()
        normalized = re.sub(r"\s+(?:[IVX]+\s*&\s*[IVX]+|\d+-\d+)$", "", normalized).strip()
        if normalized.endswith("s") and not normalized.endswith("ois") and len(normalized) > 2:
            normalized = normalized[:-1]
        return normalized or None

    def _normalize_short_partcombine_label(self, label: str | None) -> str | None:
        if label is None:
            return None
        normalized = re.sub(r"\s+(?:[IVX]+\s*&\s*[IVX]+|\d+-\d+)$", "", label).strip()
        return normalized or None

    def _partcombine_suffix(self, voice_name: str, member_index: int) -> str:
        match = re.search(r"([IVX]+|\d+)$", voice_name)
        if match:
            return match.group(1)
        return ("I", "II", "III", "IV")[member_index - 1] if member_index <= 4 else str(member_index)

    def _humanize_voice_name(self, voice_name: str) -> str:
        stem = re.sub(r"([IVX]+|\d+)$", "", voice_name)
        if not stem:
            return voice_name
        return stem[:1].upper() + stem[1:]

    def _extract_part_names(self, with_node: items.With | None) -> tuple[str | None, str | None]:
        if with_node is None:
            return None, None

        name = None
        short_name = None
        for child in with_node:
            if not isinstance(child, items.Assignment):
                continue
            assignment_name = str(child.name())
            value = self._extract_text(child.value())
            if assignment_name == "instrumentName":
                name = value
            elif assignment_name == "shortInstrumentName":
                short_name = value
        return name, short_name

    def _parse_global_settings(
        self,
        music_node: items.Item | None,
        diagnostics: list[Diagnostic],
        global_name: str,
        initial_state: _WalkState | None = None,
    ) -> _GlobalSettings:
        if not isinstance(music_node, items.Item):
            diagnostics.append(
                Diagnostic(
                    code="missing-global",
                    message=f"Unable to resolve global assignment: {global_name}",
                    severity="error",
                )
            )
            return _GlobalSettings()

        settings = _GlobalSettings()
        for flattened in self._iter_linear_nodes(music_node, initial_state or _WalkState()):
            node = flattened.node
            if isinstance(node, items.TimeSignature):
                settings.time_signature = (node.numerator(), int(1 / node.fraction()))
            elif isinstance(node, items.KeySignature):
                pitch = node.pitch()
                settings.key_mode = node.mode() or "major"
                settings.key_fifths = self._key_fifths(pitch, settings.key_mode, flattened.transpose_specs)
            elif isinstance(node, items.Tempo):
                settings.tempo_text = self._extract_text(node.text())

        self._parse_raw_global_settings(music_node, settings, initial_state or _WalkState())
        return settings

    def _parse_raw_global_settings(self, node: items.Item, settings: _GlobalSettings, state: _WalkState) -> None:
        if isinstance(node, items.Transpose):
            children = [child for child in node if isinstance(child, items.Item)]
            if len(children) >= 3 and isinstance(children[0], items.Note) and isinstance(children[1], items.Note):
                transpose_state = replace(
                    state,
                    transpose_specs=state.transpose_specs + (self._transpose_spec(children[0].pitch, children[1].pitch),),
                )
                self._parse_raw_global_settings(children[2], settings, transpose_state)
            return

        if isinstance(node, items.MusicList):
            sequence = [child for child in node if isinstance(child, items.Item)]
            index = 0
            while index < len(sequence):
                child = sequence[index]
                next_node = sequence[index + 1] if index + 1 < len(sequence) else None
                command_name = None
                if isinstance(child, items.VoiceSeparator):
                    command_name = self._raw_command_name_until(child, getattr(next_node, "position", None) if next_node is not None else None)
                if command_name == "key" and isinstance(next_node, items.Note):
                    mode_node = sequence[index + 2] if index + 2 < len(sequence) else None
                    mode_following = sequence[index + 3] if index + 3 < len(sequence) else None
                    mode_name = None
                    if isinstance(mode_node, items.VoiceSeparator):
                        mode_name = self._raw_command_name_until(
                            mode_node,
                            getattr(mode_following, "position", None) if mode_following is not None else None,
                        )
                    if mode_name in {"major", "minor"}:
                        settings.key_mode = mode_name
                        settings.key_fifths = self._key_fifths(next_node.pitch, settings.key_mode, state.transpose_specs)
                        index += 3
                        continue
                if command_name == "time" and isinstance(next_node, items.Number):
                    parts = str(next_node.token).split("/", 1)
                    if len(parts) == 2 and all(part.isdigit() for part in parts):
                        settings.time_signature = (int(parts[0]), int(parts[1]))
                        index += 2
                        continue
                if isinstance(child, items.Item):
                    self._parse_raw_global_settings(child, settings, state)
                index += 1
            return

        if isinstance(node, (items.Absolute, items.Relative, items.Tag, items.Postfix)):
            for child in node:
                if isinstance(child, items.Item):
                    self._parse_raw_global_settings(child, settings, state)

    def _build_voice(
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
    ) -> Voice:
        voice = Voice(id=voice_id, source_name=source_name)
        current_measure = Measure(number=1)
        elapsed = Fraction(0, 1)
        timeline_position = Fraction(0, 1)
        pending_directions: list[Direction] = []
        last_event: MusicEvent | None = None
        attachment_event: MusicEvent | None = None
        pending_tie_signature: tuple[tuple[str, int, int], ...] | None = None
        active_ottava: int | None = None

        def apply_barline(style: str) -> None:
            target_measure = current_measure if current_measure.events or elapsed or not voice.measures else voice.measures[-1]
            target_measure.right_barline = style

        def finalize_measure() -> None:
            nonlocal current_measure, elapsed, last_event
            current_measure.duration = elapsed
            voice.measures.append(current_measure)
            current_measure = Measure(number=current_measure.number + 1)
            elapsed = Fraction(0, 1)
            last_event = None

        def signature_for(event: MusicEvent) -> tuple[tuple[str, int, int], ...] | None:
            if event.is_rest or not event.pitches:
                return None
            return tuple((pitch.step, pitch.alter, pitch.octave) for pitch in event.pitches)

        def add_event(event: MusicEvent, origin: items.Item | None = None) -> None:
            nonlocal attachment_event, elapsed, last_event, pending_tie_signature, timeline_position
            if pending_tie_signature is not None and signature_for(event) == pending_tie_signature:
                event.tie_stop = True
                pending_tie_signature = None

            if event.is_grace:
                current_measure.events.append(event)
                last_event = event
                attachment_event = event
                return

            remaining = event.duration
            while remaining > 0:
                available = measure_length - elapsed
                if available == 0:
                    finalize_measure()
                    available = measure_length

                if not event.is_rest and remaining > available:
                    diagnostics.append(
                        Diagnostic(
                            code="measure-overflow",
                            message=f"Voice {source_name} exceeds the measure length.",
                            severity="error",
                            location=location_from_item(origin) if origin is not None else None,
                        )
                    )
                    current_measure.events.append(self._clone_event(event, duration=remaining))
                    elapsed += remaining
                    timeline_position += remaining
                    last_event = current_measure.events[-1]
                    break

                slice_duration = remaining if remaining <= available else available
                slice_event = self._clone_event(event, duration=slice_duration)
                current_measure.events.append(slice_event)
                elapsed += slice_duration
                timeline_position += slice_duration
                remaining -= slice_duration
                last_event = slice_event
                attachment_event = slice_event
                if elapsed == measure_length:
                    finalize_measure()

        walk_state = replace(initial_state or _WalkState(), allow_cues=allow_cues, measure_length=measure_length)
        for flattened in self._iter_linear_nodes(music_node, walk_state):
            node = flattened.node
            is_grace = flattened.is_grace
            if isinstance(node, _OttavaChange):
                pending_directions.extend(self._ottava_directions(node.value, active_ottava))
                active_ottava = node.value or None
            elif isinstance(node, _BarlineChange):
                style = self._barline_style(node.value)
                if style is not None:
                    apply_barline(style)
            elif isinstance(node, _CueInsertion):
                attachment_event = None
                if node.duration <= 0:
                    continue
                if node.suppressed:
                    add_event(MusicEvent(duration=node.duration, is_rest=True), node.source_node)
                    continue
                cue_events = self._expand_cue_insertion(
                    node,
                    timeline_position,
                    measure_length,
                    assignments,
                    quote_sources,
                    diagnostics,
                )
                rendered_duration = Fraction(0, 1)
                for cue_event in cue_events:
                    add_event(cue_event, node.source_node)
                    if not cue_event.is_grace:
                        rendered_duration += cue_event.duration
                if rendered_duration < node.duration:
                    add_event(MusicEvent(duration=node.duration - rendered_duration, is_rest=True), node.source_node)
            elif isinstance(node, items.Note):
                attachment_event = None
                source_pitch = flattened.resolved_pitches[0] if flattened.resolved_pitches else node.pitch
                event = MusicEvent(
                    duration=self._duration_from_node(node.duration, flattened.scale),
                    pitches=[self._to_pitch(source_pitch, flattened.transpose_specs)],
                    is_grace=is_grace,
                    grace_slash=flattened.grace_slash,
                    directions=list(pending_directions),
                    time_modification=flattened.time_modification,
                    tuplet_start=flattened.tuplet_start,
                    tuplet_stop=flattened.tuplet_stop,
                )
                pending_directions.clear()
                add_event(event, node)
            elif isinstance(node, items.Chord):
                attachment_event = None
                chord_pitches = flattened.resolved_pitches or tuple(child.pitch for child in node if isinstance(child, items.Note))
                pitches = [self._to_pitch(source_pitch, flattened.transpose_specs) for source_pitch in chord_pitches]
                event = MusicEvent(
                    duration=self._duration_from_node(node.duration, flattened.scale),
                    pitches=pitches,
                    is_grace=is_grace,
                    grace_slash=flattened.grace_slash,
                    directions=list(pending_directions),
                    time_modification=flattened.time_modification,
                    tuplet_start=flattened.tuplet_start,
                    tuplet_stop=flattened.tuplet_stop,
                )
                pending_directions.clear()
                add_event(event, node)
            elif isinstance(node, items.Rest):
                attachment_event = None
                event = MusicEvent(
                    duration=self._duration_from_node(
                        node.duration,
                        flattened.scale,
                        token=str(node.token),
                        measure_length=measure_length,
                    ),
                    is_rest=True,
                    is_grace=is_grace,
                    grace_slash=flattened.grace_slash,
                    directions=list(pending_directions),
                    time_modification=flattened.time_modification,
                    tuplet_start=flattened.tuplet_start,
                    tuplet_stop=flattened.tuplet_stop,
                )
                pending_directions.clear()
                add_event(event, node)
            elif isinstance(node, items.Dynamic):
                direction = self._dynamic_to_direction(str(node.token))
                if direction is None:
                    continue
                if last_event is not None:
                    last_event.directions.append(direction)
                else:
                    pending_directions.append(direction)
            elif isinstance(node, items.Articulation):
                target_event = last_event or attachment_event
                if target_event is None:
                    continue
                token = str(node.token)
                articulation = ARTICULATION_MAP.get(token)
                ornament = ORNAMENT_MAP.get(token)
                if articulation:
                    target_event.articulations.append(articulation)
                elif ornament:
                    target_event.ornaments.append(ornament)
            elif isinstance(node, items.Slur):
                target_event = last_event or attachment_event
                if target_event is None:
                    continue
                if node.event == "start":
                    target_event.slur_start_count += 1
                else:
                    target_event.slur_stop_count += 1
            elif isinstance(node, items.Tie):
                target_event = last_event or attachment_event
                if target_event is None:
                    continue
                target_event.tie_start = True
                pending_tie_signature = signature_for(target_event)
            elif isinstance(node, items.Command):
                token = str(node.token)
                direction = self._dynamic_to_direction(token)
                if direction is not None:
                    if last_event is not None:
                        last_event.directions.append(direction)
                    else:
                        pending_directions.append(direction)
                    continue
                if token == "\\compressEmptyMeasures":
                    voice.compress_empty_measures = True
                    continue
                if token in IGNORED_COMMANDS:
                    continue
            elif isinstance(node, items.MusicList) and node.simultaneous:
                diagnostics.append(
                    Diagnostic(
                        code="unsupported-simultaneous-music",
                        message=f"Voice {source_name} contains simultaneous music that is not yet supported.",
                        severity="error",
                        location=location_from_item(node),
                    )
                )
            elif isinstance(node, items.Repeat):
                diagnostics.append(
                    Diagnostic(
                        code="unsupported-repeat",
                        message=f"Voice {source_name} contains a repeat that is not yet supported.",
                        severity="error",
                        location=location_from_item(node),
                    )
                )

        if current_measure.events or elapsed:
            current_measure.duration = elapsed
            voice.measures.append(current_measure)

        return voice

    def _iter_linear_nodes(self, node: items.Item, state: _WalkState | None = None) -> Iterable[_FlattenedNode]:
        state = state or _WalkState()

        if isinstance(node, items.UserCommand):
            value = node.value()
            if isinstance(value, items.Item):
                yield from self._iter_linear_nodes(value, state)
            else:
                yield _FlattenedNode(
                    node=node,
                    is_grace=state.is_grace,
                    grace_slash=state.grace_slash,
                    scale=state.scale,
                    transpose_specs=state.transpose_specs,
                )
            return

        if isinstance(node, items.AfterGrace):
            current_state = state
            for index, child in enumerate(node):
                child_state = current_state if index == 0 else replace(current_state, is_grace=True, grace_slash=False)
                for flattened, current_state in self._iter_linear_nodes_with_state(child, child_state):
                    yield flattened
            return

        if isinstance(node, items.Grace):
            grace_slash = self._grace_has_slash(node)
            current_state = state
            for child in node:
                child_state = replace(current_state, is_grace=True, grace_slash=grace_slash)
                for flattened, current_state in self._iter_linear_nodes_with_state(child, child_state):
                    yield flattened
            return

        if isinstance(node, items.Transpose):
            children = [child for child in node if isinstance(child, items.Item)]
            if len(children) >= 3 and isinstance(children[0], items.Note) and isinstance(children[1], items.Note):
                transpose_state = replace(
                    state,
                    transpose_specs=state.transpose_specs + (self._transpose_spec(children[0].pitch, children[1].pitch),),
                )
                for flattened, _ in self._iter_linear_nodes_with_state(children[2], transpose_state):
                    yield flattened
                return

        if isinstance(node, items.MusicList):
            if node.simultaneous:
                yield _FlattenedNode(
                    node=node,
                    is_grace=state.is_grace,
                    grace_slash=state.grace_slash,
                    scale=state.scale,
                    transpose_specs=state.transpose_specs,
                )
                return
            sequence = [child for child in node if isinstance(child, items.Item)]
            index = 0
            current_state = state
            while index < len(sequence):
                tag_result = self._consume_tag_filter(sequence, index, current_state)
                if tag_result is not None:
                    current_state = tag_result.remaining_state
                    for emitted_child, emitted_state in tag_result.emitted:
                        emitted_current_state = emitted_state
                        for flattened, emitted_current_state in self._iter_linear_nodes_with_state(emitted_child, emitted_current_state):
                            yield flattened
                        current_state = emitted_current_state
                    index += tag_result.consumed
                    continue

                child = sequence[index]
                if isinstance(child, items.Command) and str(child.token) == "\\killCues":
                    current_state = replace(current_state, cues_killed=True)
                    index += 1
                    continue

                ottava_change = self._parse_ottava_change(sequence, index)
                if ottava_change is not None:
                    yield _FlattenedNode(
                        node=ottava_change[0],
                        is_grace=current_state.is_grace,
                        grace_slash=current_state.grace_slash,
                        scale=current_state.scale,
                        transpose_specs=current_state.transpose_specs,
                    )
                    index += ottava_change[1]
                    continue

                barline_change = self._parse_barline_change(sequence, index)
                if barline_change is not None:
                    yield _FlattenedNode(
                        node=barline_change[0],
                        is_grace=current_state.is_grace,
                        grace_slash=current_state.grace_slash,
                        scale=current_state.scale,
                        transpose_specs=current_state.transpose_specs,
                    )
                    index += barline_change[1]
                    continue

                cue_request = self._parse_cue_insertion(sequence, index, current_state)
                if cue_request is not None:
                    yield _FlattenedNode(
                        node=cue_request[0],
                        is_grace=current_state.is_grace,
                        grace_slash=current_state.grace_slash,
                        scale=current_state.scale,
                        transpose_specs=current_state.transpose_specs,
                    )
                    index += cue_request[1]
                    continue

                for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                    yield flattened
                index += 1
            return

        if isinstance(node, items.Scaler):
            flattened_children: list[_FlattenedNode] = []
            child_state = replace(state, scale=state.scale * node.scaling)
            for child in node:
                if isinstance(child, (items.Number, items.Duration)):
                    continue
                if isinstance(child, items.Item):
                    for flattened, child_state in self._iter_linear_nodes_with_state(child, child_state):
                        flattened_children.append(flattened)

            if str(getattr(node, "token", "")) in {"\\tuplet", "\\times"}:
                modification = self._time_modification_for_scaler(node)
                musical_indices = [
                    index for index, flattened in enumerate(flattened_children) if isinstance(flattened.node, MUSICAL_NODE_TYPES)
                ]
                for index in musical_indices:
                    flattened_children[index].time_modification = modification
                if musical_indices:
                    flattened_children[musical_indices[0]].tuplet_start = True
                    flattened_children[musical_indices[-1]].tuplet_stop = True

            yield from flattened_children
            return

        if isinstance(node, items.Repeat):
            yield from self._flatten_repeat(node, state)
            return

        if isinstance(node, items.Tag):
            tag_result = self._consume_tag_filter([node], 0, state)
            if tag_result is not None:
                for emitted_child, emitted_state in tag_result.emitted:
                    for flattened, _ in self._iter_linear_nodes_with_state(emitted_child, emitted_state):
                        yield flattened
                return

        if isinstance(node, items.Relative):
            children = [child for child in node if isinstance(child, items.Item)]
            if children and isinstance(children[0], items.Note):
                current_state = replace(state, relative_reference=self._copy_pitch(children[0].pitch))
                for child in children[1:]:
                    for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                        yield flattened
                return

        if isinstance(node, items.Absolute):
            current_state = replace(state, relative_reference=None)
            for child in node:
                if isinstance(child, items.Item):
                    for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                        yield flattened
            return

        if isinstance(node, items.Postfix):
            current_state = state
            for child in node:
                if isinstance(child, items.Item):
                    for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                        yield flattened
            return

        yield self._flattened_node(node, state)

    def _flatten_repeat(self, node: items.Repeat, state: _WalkState) -> Iterable[_FlattenedNode]:
        specifier = node.specifier()
        repeat_count = node.repeat_count()
        alt = node[-1] if len(node) and isinstance(node[-1], items.Alternative) else None
        body = list(node[:-1] if alt else node)

        if specifier == "unfold":
            current_state = state
            for _ in range(repeat_count):
                for child in body:
                    if isinstance(child, items.Item):
                        for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                            yield flattened
            return

        if specifier == "volta":
            alternatives = [child for child in alt if isinstance(child, items.Item)] if alt else []
            if len(alternatives) == 1 and isinstance(alternatives[0], items.MusicList):
                alternatives = [child for child in alternatives[0] if isinstance(child, items.Item)]
            if alternatives and len(alternatives) < repeat_count:
                alternatives.extend([alternatives[-1]] * (repeat_count - len(alternatives)))

            current_state = state
            for iteration in range(repeat_count):
                for child in body:
                    if isinstance(child, items.Item):
                        for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                            yield flattened
                if alternatives:
                    for flattened, current_state in self._iter_linear_nodes_with_state(alternatives[iteration], current_state):
                        yield flattened
            return

        yield self._flattened_node(node, state)

    def _iter_linear_nodes_with_state(self, node: items.Item, state: _WalkState) -> Iterable[tuple[_FlattenedNode, _WalkState]]:
        current_state = state
        for flattened in self._iter_linear_nodes(node, current_state):
            current_state = self._advance_relative_state(current_state, flattened)
            yield flattened, current_state

    def _flattened_node(self, node: items.Item | _CueInsertion | _OttavaChange | _BarlineChange, state: _WalkState) -> _FlattenedNode:
        flattened = _FlattenedNode(
            node=node,
            is_grace=state.is_grace,
            grace_slash=state.grace_slash,
            scale=state.scale,
            transpose_specs=state.transpose_specs,
        )
        if isinstance(node, items.Note):
            flattened.resolved_pitches = (self._resolve_relative_pitch(node.pitch, state.relative_reference),)
        elif isinstance(node, items.Chord):
            flattened.resolved_pitches = self._resolve_relative_chord(node, state.relative_reference)
        return flattened

    def _advance_relative_state(self, state: _WalkState, flattened: _FlattenedNode) -> _WalkState:
        if state.relative_reference is None or not flattened.resolved_pitches:
            return state
        next_reference = flattened.resolved_pitches[0] if isinstance(flattened.node, items.Chord) else flattened.resolved_pitches[-1]
        return replace(state, relative_reference=self._copy_pitch(next_reference))

    def _resolve_relative_pitch(self, raw_pitch, reference_pitch) -> object:
        pitch = self._copy_pitch(raw_pitch)
        if reference_pitch is not None:
            pitch.makeAbsolute(reference_pitch)
        return pitch

    def _resolve_relative_chord(self, node: items.Chord, reference_pitch) -> tuple[object, ...]:
        resolved_pitches: list[object] = []
        current_reference = reference_pitch
        for child in node:
            if not isinstance(child, items.Note):
                continue
            pitch = self._resolve_relative_pitch(child.pitch, current_reference)
            resolved_pitches.append(pitch)
            current_reference = pitch
        return tuple(resolved_pitches)

    def _copy_pitch(self, raw_pitch) -> object:
        return raw_pitch.copy() if hasattr(raw_pitch, "copy") else raw_pitch

    def _parse_barline_change(
        self,
        sequence: list[items.Item],
        start_index: int,
    ) -> tuple[_BarlineChange, int] | None:
        node = sequence[start_index]
        if not isinstance(node, items.Command) or str(node.token) != "\\bar":
            return None

        value = self._extract_text(sequence[start_index + 1] if start_index + 1 < len(sequence) else None)
        if not value:
            return None

        return _BarlineChange(value=value, source_node=node), 2

    def _parse_cue_insertion(
        self,
        sequence: list[items.Item],
        start_index: int,
        state: _WalkState,
    ) -> tuple[_CueInsertion, int] | None:
        node = sequence[start_index]
        command_name: str | None = None
        if isinstance(node, items.Command):
            command_name = str(node.token).lstrip("\\")
        elif isinstance(node, items.VoiceSeparator):
            command_name = self._raw_command_name(node, sequence[start_index + 1] if start_index + 1 < len(sequence) else None)
        else:
            return None

        if command_name not in {"cueDuring", "quoteDuring"}:
            return None

        position = start_index + 1
        if position >= len(sequence):
            return None

        quote_name = self._extract_text(sequence[position])
        if not quote_name:
            return None
        position += 1

        if command_name == "cueDuring":
            if position >= len(sequence) or not isinstance(sequence[position], items.Scheme):
                return None
            position += 1

        if position >= len(sequence) or not isinstance(sequence[position], items.MusicList):
            return None

        duration = self._duration_of_music(sequence[position], state)
        suppressed = (not self.export_options.include_cues) or state.cues_killed or (not state.allow_cues)
        cue = _CueInsertion(
            quote_name=quote_name,
            duration=duration,
            source_node=node,
            suppressed=suppressed,
        )
        return cue, position - start_index + 1

    def _parse_ottava_change(
        self,
        sequence: list[items.Item],
        start_index: int,
    ) -> tuple[_OttavaChange, int] | None:
        node = sequence[start_index]
        command_name: str | None = None
        if isinstance(node, items.Command):
            command_name = str(node.token).lstrip("\\")
        elif isinstance(node, items.VoiceSeparator):
            command_name = self._raw_command_name(node, sequence[start_index + 1] if start_index + 1 < len(sequence) else None)
        else:
            return None

        if command_name != "ottava":
            return None

        value = self._extract_scheme_int(sequence[start_index + 1] if start_index + 1 < len(sequence) else None)
        if value is None:
            return None

        return _OttavaChange(value=value, source_node=node), 2

    def _raw_command_name(self, node: items.Item, next_node: items.Item | None) -> str | None:
        return self._raw_command_name_until(node, getattr(next_node, "position", None) if next_node is not None else None)

    def _raw_command_name_until(self, node: items.Item, end_position: int | None) -> str | None:
        source_text = self._source_text_for_item(node)
        start_position = getattr(node, "position", None)
        if source_text is None or start_position is None:
            return None
        if end_position is None:
            end_position = len(source_text)
        match = UNRESOLVED_COMMAND_PATTERN.match(source_text[start_position:end_position])
        if match is None:
            return None
        return match.group(1)

    def _source_span(self, item: items.Item, end_position: int | None) -> str | None:
        source_text = self._source_text_for_item(item)
        start_position = getattr(item, "position", None)
        if source_text is None or start_position is None:
            return None
        if end_position is None:
            end_position = len(source_text)
        return source_text[start_position:end_position]

    def _parse_new_context(
        self,
        sequence: list[tuple[items.Item, _WalkState]],
        start_index: int,
        container_end_position: int | None,
    ) -> _NewContextCommand | None:
        node = sequence[start_index][0]
        if not isinstance(node, items.VoiceSeparator) or start_index + 1 >= len(sequence):
            return None

        content_index = start_index + 1
        header_end_position = getattr(sequence[content_index][0], "position", None)
        if isinstance(sequence[content_index][0], items.String) and start_index + 2 < len(sequence):
            content_index = start_index + 2
            header_end_position = getattr(sequence[content_index][0], "position", None)

        snippet = self._source_span(node, header_end_position or container_end_position)
        if snippet is None:
            return None
        match = NEW_CONTEXT_PATTERN.match(snippet)
        if match is None:
            return None

        return _NewContextCommand(
            context_type=match.group(1),
            context_id=match.group(2),
            content_node=sequence[content_index][0],
            consumed=content_index - start_index + 1,
        )

    def _resolve_voice_reference(
        self,
        new_context: _NewContextCommand,
        state: _WalkState,
        assignments: dict[str, items.Item | None],
        sequence: list[tuple[items.Item, _WalkState]],
        start_index: int,
        container_end_position: int | None,
        staff_index: int,
        voice_number: int,
    ) -> _VoiceReference | None:
        next_node = sequence[start_index + new_context.consumed][0] if start_index + new_context.consumed < len(sequence) else None
        return self._voice_reference_from_node(
            new_context.content_node,
            state,
            assignments,
            next_node,
            container_end_position,
            staff_index,
            voice_number,
            new_context.context_id,
        )

    def _voice_reference_from_node(
        self,
        node: items.Item,
        state: _WalkState,
        assignments: dict[str, items.Item | None],
        next_node: items.Item | None,
        container_end_position: int | None,
        staff_index: int,
        voice_number: int,
        context_id: str | None = None,
    ) -> _VoiceReference | None:
        if isinstance(node, items.UserCommand):
            return _VoiceReference(name=node.name(), state=state, context_id=context_id)

        if isinstance(node, items.VoiceSeparator):
            command_name = self._raw_command_name_until(
                node,
                getattr(next_node, "position", None) if next_node is not None else container_end_position,
            )
            if command_name:
                return _VoiceReference(name=command_name, state=state, context_id=context_id)
            return None

        if isinstance(node, items.Item):
            inline_name = context_id or f"staff{staff_index}_voice{voice_number}"
            resolved_item = self._resolve_item_reference(node, assignments, next_node, container_end_position)
            if isinstance(resolved_item, items.Item):
                return _VoiceReference(name=inline_name, state=state, context_id=context_id, music_node=resolved_item)

        return None

    def _source_text_for_item(self, item: object) -> str | None:
        location = location_from_item(item)
        if location.file_path is None:
            return None
        source_text = self._source_text_cache.get(location.file_path)
        if source_text is None:
            source_text = self.adapter.loader.read_text(location.file_path)
            self._source_text_cache[location.file_path] = source_text
        return source_text

    def _iter_filtered_children(
        self,
        node: items.Item,
        state: _WalkState | None = None,
    ) -> Iterable[tuple[items.Item, _WalkState]]:
        state = state or _WalkState()
        sequence = [child for child in node if isinstance(child, items.Item)]
        index = 0
        current_state = state
        while index < len(sequence):
            tag_result = self._consume_tag_filter(sequence, index, current_state)
            if tag_result is not None:
                current_state = tag_result.remaining_state
                for emitted in tag_result.emitted:
                    yield emitted
                index += tag_result.consumed
                continue
            yield sequence[index], current_state
            index += 1

    def _consume_tag_filter(
        self,
        sequence: list[items.Item],
        start_index: int,
        state: _WalkState,
    ) -> _SequenceFilterResult | None:
        node = sequence[start_index]

        if isinstance(node, items.Tag):
            command_name = str(node.token).lstrip("\\")
            tag_children = [child for child in node if isinstance(child, items.Item)]
            tag_name = self._extract_tag_name(tag_children[0] if tag_children else None)
            content_nodes = tuple((child, self._state_with_removed_tag(state, tag_name)) for child in tag_children[1:])
            if command_name == "removeWithTag":
                return _SequenceFilterResult(emitted=content_nodes, remaining_state=state, consumed=1)
            if command_name == "tag":
                if tag_name in state.removed_tags:
                    return _SequenceFilterResult(emitted=(), remaining_state=state, consumed=1)
                return _SequenceFilterResult(
                    emitted=tuple((child, state) for child in tag_children[1:]),
                    remaining_state=state,
                    consumed=1,
                )
            return None

        if not isinstance(node, items.VoiceSeparator):
            return None

        next_node = sequence[start_index + 1] if start_index + 1 < len(sequence) else None
        command_name = self._raw_command_name(node, next_node)
        if command_name == "removeWithTag":
            tag_name = self._extract_tag_name(next_node)
            if tag_name is None:
                return None
            return _SequenceFilterResult(
                emitted=(),
                remaining_state=self._state_with_removed_tag(state, tag_name),
                consumed=2,
            )

        if command_name == "tag":
            tag_name = self._extract_tag_name(next_node)
            content_node = sequence[start_index + 2] if start_index + 2 < len(sequence) else None
            if tag_name is None or not isinstance(content_node, items.Item):
                return None
            if tag_name in state.removed_tags:
                return _SequenceFilterResult(emitted=(), remaining_state=state, consumed=3)
            return _SequenceFilterResult(
                emitted=((content_node, state),),
                remaining_state=state,
                consumed=3,
            )

        return None

    def _state_with_removed_tag(self, state: _WalkState, tag_name: str | None) -> _WalkState:
        if not tag_name:
            return state
        return replace(state, removed_tags=state.removed_tags | frozenset({tag_name}))

    def _extract_tag_name(self, node: items.Item | None) -> str | None:
        if node is None:
            return None
        if isinstance(node, items.String):
            return node.value()
        if isinstance(node, items.Scheme):
            text = node.get_string()
            if text:
                return text
        for child in node:
            if isinstance(child, items.Item):
                tag_name = self._extract_tag_name(child)
                if tag_name:
                    return tag_name
        if type(node).__name__ == "SchemeItem":
            return str(node.token)
        return None

    def _duration_of_music(self, node: items.Item, state: _WalkState | None = None) -> Fraction:
        state = state or _WalkState()

        if isinstance(node, items.UserCommand):
            value = node.value()
            if isinstance(value, items.Item):
                return self._duration_of_music(value, state)
            return Fraction(0, 1)

        if isinstance(node, items.AfterGrace):
            return self._duration_of_music(node[0], state) if len(node) else Fraction(0, 1)

        if isinstance(node, items.Grace):
            return Fraction(0, 1)

        if isinstance(node, items.Transpose):
            children = [child for child in node if isinstance(child, items.Item)]
            if len(children) >= 3 and isinstance(children[0], items.Note) and isinstance(children[1], items.Note):
                transpose_state = replace(
                    state,
                    transpose_specs=state.transpose_specs + (self._transpose_spec(children[0].pitch, children[1].pitch),),
                )
                return self._duration_of_music(children[2], transpose_state)
            return Fraction(0, 1)

        if isinstance(node, items.MusicList):
            if node.simultaneous:
                return max(
                    (self._duration_of_music(child, child_state) for child, child_state in self._iter_filtered_children(node, state)),
                    default=Fraction(0, 1),
                )
            total = Fraction(0, 1)
            for child, child_state in self._iter_filtered_children(node, state):
                total += self._duration_of_music(child, child_state)
            return total

        if isinstance(node, items.Scaler):
            scaled_state = replace(state, scale=state.scale * node.scaling)
            total = Fraction(0, 1)
            for child in node:
                if isinstance(child, (items.Number, items.Duration)):
                    continue
                if isinstance(child, items.Item):
                    total += self._duration_of_music(child, scaled_state)
            return total

        if isinstance(node, items.Repeat):
            total = Fraction(0, 1)
            for flattened in self._flatten_repeat(node, state):
                if isinstance(flattened.node, (items.Note, items.Rest, items.Chord, items.Skip)):
                    total += self._duration_from_node(
                        flattened.node.duration,
                        flattened.scale,
                        token=str(flattened.node.token),
                        measure_length=state.measure_length,
                    )
            return total

        if isinstance(node, items.Tag):
            tag_result = self._consume_tag_filter([node], 0, state)
            if tag_result is not None:
                total = Fraction(0, 1)
                for child, child_state in tag_result.emitted:
                    total += self._duration_of_music(child, child_state)
                return total

        if isinstance(node, (items.Absolute, items.Relative, items.Postfix)):
            total = Fraction(0, 1)
            for child in node:
                if isinstance(child, items.Item):
                    total += self._duration_of_music(child, state)
            return total

        if isinstance(node, (items.Note, items.Rest, items.Chord, items.Skip)):
            return self._duration_from_node(
                node.duration,
                state.scale,
                token=str(node.token),
                measure_length=state.measure_length,
            )

        return Fraction(0, 1)

    def _expand_cue_insertion(
        self,
        cue: _CueInsertion,
        start_offset: Fraction,
        measure_length: Fraction,
        assignments: dict[str, items.Item | None],
        quote_sources: dict[str, items.Item],
        diagnostics: list[Diagnostic],
    ) -> list[MusicEvent]:
        quote_voice = self._quote_voice(cue.quote_name, measure_length, assignments, quote_sources, diagnostics)
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

        quote_voice = self._build_voice(
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

    def _slice_voice_events(self, voice: Voice, start_offset: Fraction, duration: Fraction) -> list[MusicEvent]:
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
                    events.append(self._clone_event(event, duration=overlap_end - overlap_start, is_cue=True))
                cursor = next_cursor
                if cursor >= end_offset:
                    return events

        return events

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
            lyrics=list(event.lyrics),
        )

    def _apply_lyrics(
        self,
        voice: Voice,
        lyric_source: items.Item,
        assignments: dict[str, items.Item | None],
        initial_state: _WalkState | None = None,
        verse_number: int | None = None,
    ) -> None:
        note_events = [event for measure in voice.measures for event in measure.events if event.is_note and not event.is_grace]
        if not note_events:
            return

        lyric_tokens = list(self._iter_lyric_tokens(lyric_source, assignments, initial_state or _WalkState()))
        note_index = 0
        previous_hyphen = False
        last_lyric_event: MusicEvent | None = None

        for index, token in enumerate(lyric_tokens):
            if note_index >= len(note_events):
                break

            if token.kind == "text":
                next_kind = lyric_tokens[index + 1].kind if index + 1 < len(lyric_tokens) else None
                if previous_hyphen and next_kind == "hyphen":
                    syllabic = "middle"
                elif previous_hyphen:
                    syllabic = "end"
                elif next_kind == "hyphen":
                    syllabic = "begin"
                else:
                    syllabic = "single"

                note_event = note_events[note_index]
                note_event.lyrics.append(Lyric(text=token.text or "", syllabic=syllabic, number=verse_number))
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
            tag_result = self._consume_tag_filter([node], 0, state)
            if tag_result is not None:
                for child, child_state in tag_result.emitted:
                    yield from self._iter_lyric_tokens(child, assignments, child_state)
                return

        if isinstance(node, (items.LyricMode, items.LyricsTo, items.MusicList)):
            for child, child_state in self._iter_filtered_children(node, state):
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

    def _resolve_item_reference(
        self,
        node: items.Item | None,
        assignments: dict[str, items.Item | None],
        next_node: items.Item | None = None,
        container_end_position: int | None = None,
    ) -> items.Item | None:
        if node is None:
            return None
        if isinstance(node, items.UserCommand):
            value = node.value()
            if isinstance(value, items.Item):
                return value
            resolved = assignments.get(node.name())
            return resolved if isinstance(resolved, items.Item) else None
        if isinstance(node, items.VoiceSeparator):
            command_name = self._raw_command_name_until(
                node,
                getattr(next_node, "position", None) if next_node is not None else container_end_position,
            )
            if command_name is None:
                return None
            resolved = assignments.get(command_name)
            return resolved if isinstance(resolved, items.Item) else None
        if isinstance(node, items.Assignment):
            value = node.value()
            return value if isinstance(value, items.Item) else None
        return node

    def _extract_scheme_int(self, node: items.Item | None) -> int | None:
        if node is None:
            return None
        if isinstance(node, items.Scheme):
            get_int = getattr(node, "get_int", None)
            if callable(get_int):
                value = get_int()
                if value is not None:
                    return int(value)
        for child in node:
            if isinstance(child, items.Item):
                value = self._extract_scheme_int(child)
                if value is not None:
                    return value
        token = getattr(node, "token", None)
        if token is None:
            return None
        try:
            return int(str(token))
        except ValueError:
            return None

    def _grace_has_slash(self, node: items.Grace) -> bool:
        return str(getattr(node, "token", "")) == "\\acciaccatura"

    def _barline_style(self, value: str) -> str | None:
        return {
            "||": "light-light",
            "|.": "light-heavy",
        }.get(value)

    def _ottava_directions(self, ottava_value: int, active_ottava: int | None) -> list[Direction]:
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
        return Direction(kind="octave-shift", value=f"{placement}:{shift_type}:{size}")

    def _extract_text(self, node: items.Item | None, scheme_values: dict[str, str] | None = None) -> str | None:
        if node is None:
            return None
        if isinstance(node, items.UserCommand):
            value = node.value()
            if value is None and scheme_values is not None:
                return scheme_values.get(node.name())
            return self._extract_text(value, scheme_values)
        if isinstance(node, items.Assignment):
            return self._extract_text(node.value(), scheme_values)
        if isinstance(node, items.String):
            return node.value()
        if isinstance(node, items.Markup):
            return node.plaintext()
        if isinstance(node, items.MarkupWord):
            return node.plaintext()
        if isinstance(node, items.Scheme):
            return node.get_string() or None
        if hasattr(node, "plaintext"):
            text = node.plaintext()
            return text or None
        return None

    def _duration_from_node(
        self,
        raw_duration,
        scale: Fraction = Fraction(1, 1),
        token: str | None = None,
        measure_length: Fraction | None = None,
    ) -> Fraction:
        base, scaling = raw_duration
        if token == "R" and measure_length is not None:
            return measure_length * scaling * scale
        return base * scaling * scale

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

    def _time_modification_for_scaler(self, node: items.Scaler) -> tuple[int, int]:
        token = str(getattr(node, "token", ""))
        if token == "\\tuplet":
            return node.numerator, node.denominator
        return node.denominator, node.numerator

    def _to_pitch(self, raw_pitch, transpose_specs: tuple[_TransposeSpec, ...] = ()) -> Pitch:
        note, alter, octave = self._pitch_components(raw_pitch, transpose_specs)
        return Pitch(step=STEP_MAP[note], alter=alter, octave=octave)

    def _key_fifths(self, pitch, mode: str, transpose_specs: tuple[_TransposeSpec, ...] = ()) -> int:
        if pitch is None:
            return 0
        note, alter, _ = self._pitch_components(pitch, transpose_specs)
        return KEY_FIFTHS.get((note, alter, mode), 0)

    def _pitch_components(self, raw_pitch, transpose_specs: tuple[_TransposeSpec, ...] = ()) -> tuple[int, int, int]:
        note = int(getattr(raw_pitch, "note", 0))
        alter = Fraction(getattr(raw_pitch, "alter", 0))
        octave = int(getattr(raw_pitch, "octave", 0))
        for spec in transpose_specs:
            note, alter, octave = self._apply_transpose_spec(note, alter, octave, spec)
        return note, int(alter), octave + 4

    def _transpose_spec(self, from_pitch, to_pitch) -> _TransposeSpec:
        from_note = int(getattr(from_pitch, "note", 0))
        to_note = int(getattr(to_pitch, "note", 0))
        from_alter = Fraction(getattr(from_pitch, "alter", 0))
        to_alter = Fraction(getattr(to_pitch, "alter", 0))
        from_octave = int(getattr(from_pitch, "octave", 0))
        to_octave = int(getattr(to_pitch, "octave", 0))
        return _TransposeSpec(
            octave=to_octave - from_octave,
            steps=to_note - from_note,
            alter=PITCH_SCALE[to_note] + to_alter - PITCH_SCALE[from_note] - from_alter,
        )

    def _apply_transpose_spec(self, note: int, alter: Fraction, octave: int, spec: _TransposeSpec) -> tuple[int, Fraction, int]:
        doct, transposed_note = divmod(note + spec.steps, 7)
        transposed_alter = alter + spec.alter - doct * 12 - PITCH_SCALE[transposed_note] + PITCH_SCALE[note]
        transposed_octave = octave + spec.octave + doct

        while transposed_alter > 1:
            doct, next_note = divmod(transposed_note + 1, 7)
            transposed_alter -= doct * 12 + PITCH_SCALE[next_note] - PITCH_SCALE[transposed_note]
            transposed_octave += doct
            transposed_note = next_note
        while transposed_alter < -1:
            doct, next_note = divmod(transposed_note - 1, 7)
            transposed_alter += doct * -12 + PITCH_SCALE[transposed_note] - PITCH_SCALE[next_note]
            transposed_octave += doct
            transposed_note = next_note

        return transposed_note, transposed_alter, transposed_octave

    def _compute_divisions(self, part: Part) -> int:
        denominators: list[int] = []
        for voice in part.voices:
            for measure in voice.measures:
                for event in measure.events:
                    denominators.append(event.duration.denominator)
        if not denominators:
            return 1
        result = 1
        for denominator in denominators:
            result = lcm(result, denominator)
        return result
