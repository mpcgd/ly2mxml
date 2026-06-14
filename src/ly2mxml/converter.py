"""Convert parsed LilyPond projects into the internal score model.

This module holds the semantic heart of the project. It translates the
python-ly parser tree into a simpler score representation that captures the
bounded LilyPond surface supported by the repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction
from math import lcm
from pathlib import Path
import re
from typing import Iterable, Iterator, Mapping

from ly.music import items

from ly2mxml._types import (
    _BarlineChange,
    _CueInsertion,
    _FlattenedNode,
    _GlobalSettings,
    _LyricToken,
    _NewContextCommand,
    _OttavaChange,
    _PartBuildContext,
    _PartCombinePlan,
    _PartialDuration,
    _SecondaryVoiceBlocks,
    _SequenceFilterResult,
    _StaffPartPlan,
    _StaffPlanningState,
    _TransposeSpec,
    _VoiceBuildState,
    _VoiceReference,
    _WalkState,
    _RehearsalMark,
)
from ly2mxml.diagnostics import Diagnostic, location_from_item
from ly2mxml.frontend.python_ly_adapter import PythonLyAdapter, SourceAnalysis
from ly2mxml.model.score import ClefChange, Direction, KeyChange, Lyric, Measure, MusicEvent, Part, PartCombineMode, Pitch, Score, ScoreMetadata, TimeChange, Voice
from ly2mxml.musicxml.writer import MusicXmlWriter
from ly2mxml.options import ExportOptions
from ly2mxml import state_resolver as _sr
from ly2mxml.linearizer import Linearizer, MUSICAL_NODE_TYPES, NEW_CONTEXT_PATTERN, UNRESOLVED_COMMAND_PATTERN
from ly2mxml.voice_builder import (
    VoiceBuilder,
    ARTICULATION_MAP,
    CODA_SEGNO_COMMANDS,
    DYNAMIC_MARKS,
    FERMATA_MAP,
    ORNAMENT_MAP,
    PERFORMANCE_TEXT_MARKS,
    TECHNICAL_MAP,
    TEXT_DYNAMICS,
    VOICE_COMMAND_STEMS,
    WEDGE_DYNAMICS,
)


KNOWN_BUILTIN_USER_COMMANDS = {
    "addQuote",
    "arpeggio",
    "breathe",
    "compressEmptyMeasures",
    "glissando",
    "killCues",
    "mark",
    "ottava",
    "partCombine",
    "removeWithTag",
    "keepWithTag",
    "rf",
    "sff",
    "sffz",
    "sfpp",
    "tag",
    "tremblement",
    "haydn",
}

STAFF_GROUP_SYMBOLS: dict[str, str] = {
    "StaffGroup": "bracket",
    "ChoirStaff": "bracket",
    "GrandStaff": "brace",
    "PianoStaff": "brace",
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
    "repeat:tremolo",
    "repeat:unfold",
    "repeat:volta",
    "scaled-durations",
    "scheme",
    "tag-filtering",
    "transpose",
    "user-variables",
}

UNSUPPORTED_FEATURE_MESSAGES = {}

# These constants are defined once in state_resolver and re-exported here for
# backward compatibility with any code that imports them from this module.
DEFAULT_CLEF = _sr.DEFAULT_CLEF
CLEF_MAP = _sr.CLEF_MAP
STEP_MAP = _sr.STEP_MAP
KEY_FIFTHS = _sr.KEY_FIFTHS
PITCH_SCALE = _sr.PITCH_SCALE
BEAT_UNIT_MAP = _sr.BEAT_UNIT_MAP

# ARTICULATION_MAP, CODA_SEGNO_COMMANDS, DYNAMIC_MARKS, FERMATA_MAP,
# ORNAMENT_MAP, PERFORMANCE_TEXT_MARKS, TECHNICAL_MAP, TEXT_DYNAMICS,
# VOICE_COMMAND_STEMS, WEDGE_DYNAMICS are imported from ly2mxml.voice_builder.

DEFINE_PUBLIC_STRING_PATTERN = re.compile(r'#\(define-public\s+([\w-]+)\s+"([^"]*)"\)')
# NEW_CONTEXT_PATTERN, UNRESOLVED_COMMAND_PATTERN, MUSICAL_NODE_TYPES are imported
# from ly2mxml.linearizer (where they live alongside the Linearizer class).


@dataclass(slots=True)
class ConversionPreflight:
    """Summarize inspection results and conversion blockers before export."""

    analysis: SourceAnalysis
    diagnostics: list[Diagnostic] = field(default_factory=list)
    supported_features: set[str] = field(default_factory=set)
    unsupported_features: set[str] = field(default_factory=set)

    @property
    def has_errors(self) -> bool:
        """Return ``True`` when preflight found at least one error."""

        return any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


@dataclass(slots=True)
class ConversionResult:
    """Bundle the preflight, converted score, and optional output path."""

    preflight: ConversionPreflight
    score: Score | None = None
    output_path: Path | None = None


class LilypondConverter:
    """Orchestrate LilyPond inspection, semantic conversion, and XML writing.

    The converter performs three distinct jobs:

    - inspect a project and classify feature usage before export
    - flatten supported LilyPond constructs into the intermediate score model
    - delegate final serialization to the MusicXML writer
    """

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
            raise ValueError(
                f"Conflicting partcombine_mode: positional argument '{partcombine_mode}' "
                f"differs from export_options.partcombine_mode '{export_options.partcombine_mode}'. "
                "Pass the mode in one place only."
            )

        self.export_options = export_options
        self.partcombine_mode = export_options.partcombine_mode
        self._source_text_cache: dict[Path, str] = {}
        self._scheme_values_cache: dict[Path, dict[str, str]] = {}
        self._lz = Linearizer(self.adapter.loader, self._source_text_cache, self.export_options)
        self._vb = VoiceBuilder(self._lz, self.export_options)

    def preflight(self, entrypoint: str | Path) -> ConversionPreflight:
        """Inspect a LilyPond project and classify known unsupported features."""

        analysis = self.adapter.inspect(entrypoint)
        scheme_values = self._collect_define_public_strings(self.adapter.load_document_tree(entrypoint))
        diagnostics: list[Diagnostic] = []
        supported_features: set[str] = set()
        unsupported_features: set[str] = set()

        for diagnostic in analysis.diagnostics:
            if diagnostic.code == "unresolved-user-command":
                name = diagnostic.message.rsplit("\\", 1)[-1]
                if name in KNOWN_BUILTIN_USER_COMMANDS or name in scheme_values or name in analysis.assignments:
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
        """Convert one LilyPond entrypoint into the internal score model."""

        document = self.adapter.load_document_tree(entrypoint)
        # These discovery passes establish the cross-reference tables the rest
        # of the converter relies on: user variables, cue quote sources, and
        # top-level metadata all need to be known before staff traversal starts.
        assignments = self._collect_assignments(document)
        quote_sources = self._collect_quotes(document, assignments)
        scheme_values = self._collect_define_public_strings(document)
        metadata = self._extract_metadata(document, scheme_values)
        score_node = self._first_score(document)
        diagnostics: list[Diagnostic] = []
        # Fresh VoiceBuilder resets the rehearsal-mark counter and quote cache.
        self._vb = VoiceBuilder(self._lz, self.export_options)

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
        # Staff contexts are the closest LilyPond structure to exported parts,
        # so score assembly starts there and only then resolves voice planning
        # and optional partCombine grouping inside each staff.
        current_group_id: int | None = None
        current_group_parts: list[Part] = []
        for staff_index, (staff_context, walk_state, group_id, group_symbol) in enumerate(self._iter_staff_contexts(score_node), start=1):
            built_parts = self._build_parts(
                staff_context,
                staff_index,
                next_part_index,
                assignments,
                quote_sources,
                diagnostics,
                walk_state,
            )
            added: list[Part] = []
            for part in built_parts:
                if part.voices:
                    part.divisions = self._compute_divisions(part)
                    parts.append(part)
                    added.append(part)
            next_part_index += len(built_parts)

            # Track group boundaries and annotate parts accordingly.
            if group_id != current_group_id:
                if current_group_parts:
                    current_group_parts[-1].group_stop = True
                current_group_id = group_id
                current_group_parts = []
                if group_id is not None and added:
                    added[0].group_start = group_symbol
            if group_id is not None:
                current_group_parts.extend(added)

        # Close any group still open after the last staff.
        if current_group_parts:
            current_group_parts[-1].group_stop = True

        return Score(metadata=metadata, parts=parts, diagnostics=diagnostics)

    def convert_file(self, entrypoint: str | Path, output_path: str | Path) -> ConversionResult:
        """Run preflight, build the score, and write MusicXML when safe."""

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

        def visit(doc: items.Document) -> None:
            for node in doc:
                if isinstance(node, items.Assignment):
                    assignments[str(node.name())] = node.value()

        self._visit_documents(document, visit)
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

        def visit(doc: items.Document) -> None:
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
                index += 1

        self._visit_documents(document, visit)
        return quotes

    def _collect_define_public_strings(self, document: items.Document) -> dict[str, str]:
        raw_root_name = getattr(document.document, "filename", None)
        cache_key = Path(raw_root_name).resolve() if raw_root_name else None
        if cache_key is not None and cache_key in self._scheme_values_cache:
            return self._scheme_values_cache[cache_key]

        values: dict[str, str] = {}

        def visit(doc: items.Document) -> None:
            raw_file_name = getattr(doc.document, "filename", None)
            resolved_file_name = Path(raw_file_name).resolve() if raw_file_name else None
            if resolved_file_name is not None:
                source_text = self.adapter.loader.read_text(resolved_file_name)
                for name, value in DEFINE_PUBLIC_STRING_PATTERN.findall(source_text):
                    values[name] = value

        self._visit_documents(document, visit)
        if cache_key is not None:
            self._scheme_values_cache[cache_key] = values
        return values

    def _visit_documents(self, document: items.Document, visitor: callable) -> None:
        visited_paths: set[Path] = set()

        def visit(doc: items.Document) -> None:
            raw_file_name = getattr(doc.document, "filename", None)
            resolved_file_name = Path(raw_file_name).resolve() if raw_file_name else None
            if resolved_file_name in visited_paths:
                return
            if resolved_file_name is not None:
                visited_paths.add(resolved_file_name)

            visitor(doc)

            for node in doc:
                if isinstance(node, items.Include):
                    included = self.adapter.load_included_document(doc, node)
                    if included is not None:
                        visit(included)

        visit(document)

    def _first_score(self, document: items.Document) -> items.Score | None:
        for node in document:
            if isinstance(node, items.Score):
                return node
        return None

    def _iter_staff_contexts(
        self,
        node: items.Item,
        state: _WalkState | None = None,
        group_id: int | None = None,
        group_symbol: str | None = None,
    ) -> Iterator[tuple[items.Context, _WalkState, int | None, str | None]]:
        """Yield each ``Staff`` context together with walk state and group info."""

        state = state or _WalkState()
        if isinstance(node, items.Context) and node.context() == "Staff":
            yield node, state, group_id, group_symbol
            return
        if isinstance(node, items.Context) and node.context() in STAFF_GROUP_SYMBOLS:
            new_group_id = id(node)
            new_group_symbol = STAFF_GROUP_SYMBOLS[node.context()]
            for child, child_state in self._iter_filtered_children(node, state):
                yield from self._iter_staff_contexts(child, child_state, new_group_id, new_group_symbol)
            return
        # Unwrap UserCommand nodes so that indirect references like
        #   violinPart = \new Staff { ... }
        #   \score { \violinPart }
        # resolve to the underlying Staff context.
        if isinstance(node, items.UserCommand):
            value = node.value()
            if isinstance(value, items.Item):
                yield from self._iter_staff_contexts(value, state, group_id, group_symbol)
                return
        for child, child_state in self._iter_filtered_children(node, state):
            yield from self._iter_staff_contexts(child, child_state, group_id, group_symbol)

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
        """Build the exported parts that originate from one LilyPond staff."""

        part_plan = self._plan_staff_parts(
            staff_context,
            staff_index,
            assignments,
            diagnostics,
            initial_state,
        )
        with_node = next((child for child in staff_context if isinstance(child, items.With)), None)
        built_parts: list[Part] = []
        next_part_index = start_part_index

        if part_plan.partcombine_groups:
            for group in part_plan.partcombine_groups:
                group_parts, next_part_index = self._build_partcombine_member_parts(
                    group,
                    part_plan.part_context,
                    next_part_index,
                    assignments,
                    quote_sources,
                    diagnostics,
                    part_plan.lyric_sources,
                )
                built_parts.extend(group_parts)

        if part_plan.voice_refs:
            built_parts.append(
                self._build_standalone_part(
                    list(part_plan.voice_refs),
                    part_plan.part_context,
                    next_part_index,
                    assignments,
                    quote_sources,
                    diagnostics,
                    part_plan.lyric_sources,
                )
            )

        return built_parts

    def _plan_staff_parts(
        self,
        staff_context: items.Context,
        staff_index: int,
        assignments: dict[str, items.Item | None],
        diagnostics: list[Diagnostic],
        initial_state: _WalkState,
    ) -> _StaffPartPlan:
        """Plan how one staff should expand into exported parts and voices."""

        with_node = next((child for child in staff_context if isinstance(child, items.With)), None)
        music_node = next((child for child in staff_context if isinstance(child, items.Music)), None)

        name, short_name = self._extract_part_names(with_node)
        clef_spec = DEFAULT_CLEF
        opening_clef_locked = False
        planning_state = _StaffPlanningState(global_ref=_VoiceReference("global", initial_state))
        container_end_position = music_node.end_position() if music_node is not None and callable(getattr(music_node, "end_position", None)) else None

        if isinstance(music_node, items.MusicList):
            sequence = list(self._iter_filtered_children(music_node, initial_state))
        elif isinstance(music_node, items.Item):
            sequence = [(music_node, initial_state)]
        else:
            sequence = []

        position = 0
        # Planning is intentionally separate from voice building. This keeps the
        # exported part topology stable before any note-level flattening starts,
        # which is especially important for ``\partCombine`` and lyric routing.
        while position < len(sequence):
            node, node_state = sequence[position]
            if isinstance(node, items.Context):
                handled, voice_ref = self._handle_explicit_staff_context(
                    node,
                    node_state,
                    sequence,
                    position,
                    assignments,
                    staff_index,
                    container_end_position,
                    planning_state,
                )
                if handled:
                    if voice_ref is not None:
                        planning_state.voice_refs.append(voice_ref)
                        planning_state.last_voice_ref = voice_ref
                    position += 1
                    continue

            new_context = self._parse_new_context(sequence, position, container_end_position)
            if new_context is not None:
                voice_ref = self._handle_new_staff_context(
                    new_context,
                    node_state,
                    sequence,
                    position,
                    assignments,
                    staff_index,
                    container_end_position,
                    planning_state,
                )
                if voice_ref is not None:
                    planning_state.voice_refs.append(voice_ref)
                    planning_state.last_voice_ref = voice_ref
                position += new_context.consumed
                continue

            if isinstance(node, items.Clef):
                if opening_clef_locked:
                    position += 1
                    continue
                resolved_clef = _sr.resolve_clef(node.specifier())
                if resolved_clef is None:
                    diagnostics.append(
                        Diagnostic(
                            code="unsupported-clef",
                            message=f"Unsupported clef in staff {staff_index}: {node.specifier()}",
                            severity="warning",
                            location=location_from_item(node),
                        )
                    )
                    position += 1
                    continue
                clef_spec = resolved_clef
                opening_clef_locked = True
            elif isinstance(node, items.Command) and str(node.token) == "\\partCombine":
                self._plan_partcombine_group(
                    sequence,
                    position,
                    assignments,
                    staff_index,
                    container_end_position,
                    name,
                    short_name,
                    planning_state,
                )
                position += 2
            elif isinstance(node, items.UserCommand):
                self._register_planning_named_reference(
                    node.name(),
                    node_state,
                    planning_state,
                )
            elif isinstance(node, items.VoiceSeparator):
                self._register_voice_separator_reference(
                    node,
                    node_state,
                    sequence,
                    position,
                    container_end_position,
                    planning_state,
                )
            elif isinstance(node, items.LyricMode) and str(node.token) == "\\addlyrics":
                self._register_addlyrics_source(node, planning_state)
            position += 1

        global_settings = self._parse_global_settings(
            assignments.get(planning_state.global_ref.name),
            diagnostics,
            planning_state.global_ref.name,
            planning_state.global_ref.state,
        )
        clef_sign, clef_line, clef_octave_change = clef_spec
        return _StaffPartPlan(
            part_context=_PartBuildContext(
                staff_index=staff_index,
                name=name,
                short_name=short_name,
                clef_sign=clef_sign,
                clef_line=clef_line,
                clef_octave_change=clef_octave_change,
                global_settings=global_settings,
            ),
            voice_refs=tuple(planning_state.voice_refs),
            partcombine_groups=tuple(planning_state.partcombine_groups),
            lyric_sources=planning_state.lyric_sources,
        )

    def _handle_explicit_staff_context(
        self,
        node: items.Context,
        node_state: _WalkState,
        sequence: list[tuple[items.Item, _WalkState]],
        position: int,
        assignments: dict[str, items.Item | None],
        staff_index: int,
        container_end_position: int | None,
        planning_state: _StaffPlanningState,
    ) -> tuple[bool, _VoiceReference | None]:
        context_name = node.context()
        if context_name == "Voice":
            voice_child = next((child for child in node if isinstance(child, items.Item)), None)
            if voice_child is None:
                return True, None
            return True, self._voice_reference_from_node(
                voice_child,
                node_state,
                assignments,
                self._sequence_item_at(sequence, position + 1),
                container_end_position,
                staff_index,
                self._next_planned_voice_number(planning_state),
                node.context_id(),
            )
        if context_name == "Lyrics":
            lyric_child = next((child for child in node if isinstance(child, items.Item)), None)
            if lyric_child is not None:
                self._register_lyric_source(
                    lyric_child,
                    node_state,
                    assignments,
                    self._sequence_item_at(sequence, position + 1),
                    container_end_position,
                    planning_state.lyric_sources,
                )
            return True, None
        return False, None

    def _handle_new_staff_context(
        self,
        new_context: _NewContextCommand,
        node_state: _WalkState,
        sequence: list[tuple[items.Item, _WalkState]],
        position: int,
        assignments: dict[str, items.Item | None],
        staff_index: int,
        container_end_position: int | None,
        planning_state: _StaffPlanningState,
    ) -> _VoiceReference | None:
        if new_context.context_type == "Voice":
            return self._resolve_voice_reference(
                new_context,
                node_state,
                assignments,
                sequence,
                position,
                container_end_position,
                staff_index,
                self._next_planned_voice_number(planning_state),
            )
        if new_context.context_type == "Lyrics":
            next_node = self._sequence_item_at(sequence, position + new_context.consumed)
            self._register_lyric_source(
                new_context.content_node,
                node_state,
                assignments,
                next_node,
                container_end_position,
                planning_state.lyric_sources,
            )
        return None

    def _plan_partcombine_group(
        self,
        sequence: list[tuple[items.Item, _WalkState]],
        position: int,
        assignments: dict[str, items.Item | None],
        staff_index: int,
        container_end_position: int | None,
        name: str | None,
        short_name: str | None,
        planning_state: _StaffPlanningState,
    ) -> None:
        left = sequence[position + 1] if position + 1 < len(sequence) else None
        right = sequence[position + 2] if position + 2 < len(sequence) else None
        planned_voice_refs: list[_VoiceReference] = []
        updated_last_voice_ref = planning_state.last_voice_ref
        if left is not None:
            left_ref = self._voice_reference_from_node(
                left[0],
                left[1],
                assignments,
                self._sequence_item_at(sequence, position + 3),
                container_end_position,
                staff_index,
                self._next_planned_voice_number(
                    planning_state,
                    additional_group_voice_count=len(planned_voice_refs),
                ),
            )
            if left_ref is not None:
                planned_voice_refs.append(left_ref)
                updated_last_voice_ref = left_ref
        if right is not None:
            right_ref = self._voice_reference_from_node(
                right[0],
                right[1],
                assignments,
                self._sequence_item_at(sequence, position + 4),
                container_end_position,
                staff_index,
                self._next_planned_voice_number(
                    planning_state,
                    additional_group_voice_count=len(planned_voice_refs),
                ),
            )
            if right_ref is not None:
                planned_voice_refs.append(right_ref)
                updated_last_voice_ref = right_ref
        if len(planned_voice_refs) == 2:
            inferred_names, inferred_short_names = self._infer_partcombine_labels(
                name,
                short_name,
                [voice_ref.name for voice_ref in planned_voice_refs],
            )
            planning_state.partcombine_groups.append(
                _PartCombinePlan(
                    voice_refs=tuple(planned_voice_refs),
                    names=tuple(inferred_names),
                    short_names=tuple(inferred_short_names),
                    group_id=f"staff-{staff_index}-combine-{len(planning_state.partcombine_groups) + 1}",
                )
            )
        else:
            planning_state.voice_refs.extend(planned_voice_refs)
        planning_state.last_voice_ref = updated_last_voice_ref

    def _next_planned_voice_number(
        self,
        planning_state: _StaffPlanningState,
        additional_group_voice_count: int = 0,
    ) -> int:
        return (
            len(planning_state.voice_refs)
            + sum(len(group.voice_refs) for group in planning_state.partcombine_groups)
            + additional_group_voice_count
            + 1
        )

    def _sequence_item_at(
        self,
        sequence: list[tuple[items.Item, _WalkState]],
        index: int,
    ) -> items.Item | None:
        if 0 <= index < len(sequence):
            return sequence[index][0]
        return None

    def _register_lyric_source(
        self,
        lyric_node: items.Item,
        state: _WalkState,
        assignments: dict[str, items.Item | None],
        next_node: items.Item | None,
        container_end_position: int | None,
        lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]],
    ) -> None:
        lyric_reference = self._resolve_item_reference(
            lyric_node,
            assignments,
            next_node,
            container_end_position,
        )
        if isinstance(lyric_reference, items.LyricsTo):
            target = lyric_reference.context_id()
            if target:
                lyric_sources.setdefault(target, []).append((lyric_reference, state))
        elif isinstance(lyric_reference, items.MusicList) and not lyric_reference.simultaneous:
            # Handle inline block form: \new Lyrics { \lyricsto "voice" { words } }
            # The MusicList wrapper contains one or more LyricsTo children.
            for child in lyric_reference:
                if isinstance(child, items.LyricsTo):
                    target = child.context_id()
                    if target:
                        lyric_sources.setdefault(target, []).append((child, state))

    def _build_partcombine_member_parts(
        self,
        group: _PartCombinePlan,
        part_context: _PartBuildContext,
        start_part_index: int,
        assignments: dict[str, items.Item | None],
        quote_sources: dict[str, items.Item],
        diagnostics: list[Diagnostic],
        lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]],
    ) -> tuple[list[Part], int]:
        built_parts: list[Part] = []
        next_part_index = start_part_index
        for member_index, voice_ref in enumerate(group.voice_refs, start=1):
            part = self._create_part(
                next_part_index,
                part_context,
                name=group.names[member_index - 1],
                short_name=group.short_names[member_index - 1],
                combine_group=group.group_id,
                combine_member=member_index,
                combined_name=part_context.name or f"Part {part_context.staff_index}",
                combined_short_name=part_context.short_name,
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
        return built_parts, next_part_index

    def _build_standalone_part(
        self,
        voice_refs: list[_VoiceReference],
        part_context: _PartBuildContext,
        part_index: int,
        assignments: dict[str, items.Item | None],
        quote_sources: dict[str, items.Item],
        diagnostics: list[Diagnostic],
        lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]],
    ) -> Part:
        part = self._create_part(
            part_index,
            part_context,
            name=part_context.name or f"Part {part_context.staff_index}",
            short_name=part_context.short_name,
        )
        for voice_ref in voice_refs:
            self._append_part_voice(
                part,
                voice_ref,
                str(len(part.voices) + 1),
                assignments,
                quote_sources,
                diagnostics,
                lyric_sources,
            )
        return part

    def _register_named_reference(
        self,
        command_name: str | None,
        state: _WalkState,
        voice_refs: list[_VoiceReference],
        global_ref: _VoiceReference,
        last_voice_ref: _VoiceReference | None,
    ) -> tuple[_VoiceReference, _VoiceReference | None]:
        if command_name in {"global", "globalNoKey"}:
            return _VoiceReference(command_name, state), last_voice_ref
        if command_name and command_name not in KNOWN_BUILTIN_USER_COMMANDS:
            voice_ref = _VoiceReference(command_name, state)
            voice_refs.append(voice_ref)
            return global_ref, voice_ref
        return global_ref, last_voice_ref

    def _register_planning_named_reference(
        self,
        command_name: str | None,
        state: _WalkState,
        planning_state: _StaffPlanningState,
    ) -> None:
        planning_state.global_ref, planning_state.last_voice_ref = self._register_named_reference(
            command_name,
            state,
            planning_state.voice_refs,
            planning_state.global_ref,
            planning_state.last_voice_ref,
        )

    def _register_voice_separator_reference(
        self,
        node: items.VoiceSeparator,
        state: _WalkState,
        sequence: list[tuple[items.Item, _WalkState]],
        position: int,
        container_end_position: int | None,
        planning_state: _StaffPlanningState,
    ) -> None:
        next_node = self._sequence_item_at(sequence, position + 1)
        command_name = self._raw_command_name_until(
            node,
            getattr(next_node, "position", None) if next_node is not None else container_end_position,
        )
        self._register_planning_named_reference(command_name, state, planning_state)

    def _register_addlyrics_source(
        self,
        node: items.LyricMode,
        planning_state: _StaffPlanningState,
    ) -> None:
        if planning_state.last_voice_ref is None:
            return
        planning_state.lyric_sources.setdefault(planning_state.last_voice_ref.lyric_target, []).append(
            (node, planning_state.last_voice_ref.state)
        )

    def _create_part(
        self,
        part_index: int,
        part_context: _PartBuildContext,
        name: str,
        short_name: str | None,
        combine_group: str | None = None,
        combine_member: int | None = None,
        combined_name: str | None = None,
        combined_short_name: str | None = None,
    ) -> Part:
        settings = part_context.global_settings
        return Part(
            id=f"P{part_index}",
            name=name,
            short_name=short_name,
            clef_sign=part_context.clef_sign,
            clef_line=part_context.clef_line,
            time_signature=settings.time_signature,
            key_fifths=settings.key_fifths,
            key_mode=settings.key_mode,
            clef_octave_change=part_context.clef_octave_change,
            tempo_text=settings.tempo_text,
            combine_group=combine_group,
            combine_member=combine_member,
            combined_name=combined_name,
            combined_short_name=combined_short_name,
        )

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

        # Detect voice-separator shorthand: << { v1 } \\ { v2 } ... >>
        if isinstance(voice_music, items.MusicList) and voice_music.simultaneous:
            sub_blocks = self._split_voice_separator_block(voice_music)
            if sub_blocks is not None:
                for sub_index, sub_block in enumerate(sub_blocks, start=1):
                    sub_voice = self._vb.build_voice(
                        voice_id=f"{voice_id}_{sub_index}",
                        source_name=voice_ref.name,
                        music_node=sub_block,
                        measure_length=part.measure_length,
                        assignments=assignments,
                        quote_sources=quote_sources,
                        diagnostics=diagnostics,
                        initial_state=voice_ref.state,
                        initial_clef=(part.clef_sign, part.clef_line, part.clef_octave_change),
                        initial_key_fifths=part.key_fifths,
                        initial_key_mode=part.key_mode,
                        initial_time_signature=part.time_signature,
                    )
                    if not part.voices:
                        self._promote_opening_voice_clef(part, sub_voice)
                    part.voices.append(sub_voice)
                return

        voice = self._vb.build_voice(
            voice_id=voice_id,
            source_name=voice_ref.name,
            music_node=voice_music,
            measure_length=part.measure_length,
            assignments=assignments,
            quote_sources=quote_sources,
            diagnostics=diagnostics,
            initial_state=voice_ref.state,
            initial_clef=(part.clef_sign, part.clef_line, part.clef_octave_change),
            initial_key_fifths=part.key_fifths,
            initial_key_mode=part.key_mode,
            initial_time_signature=part.time_signature,
            out_extra_voices=(extra_voices := []),
        )
        if not part.voices:
            self._promote_opening_voice_clef(part, voice)
        target_lyrics = lyric_sources.get(voice_ref.lyric_target, [])
        for verse_index, (lyric_source, lyric_state) in enumerate(target_lyrics, start=1):
            verse_number = verse_index if len(target_lyrics) > 1 else None
            self._vb._apply_lyrics(voice, lyric_source, assignments, lyric_state, verse_number, diagnostics)
        part.voices.append(voice)
        for extra_voice in extra_voices:
            extra_voice.id = str(len(part.voices) + 1)
            part.voices.append(extra_voice)

    def _split_voice_separator_block(
        self,
        music_list: items.MusicList,
    ) -> list[items.MusicList] | None:
        return self._lz._split_voice_separator_block(music_list)

    def _promote_opening_voice_clef(self, part: Part, voice: Voice) -> None:
        if not voice.measures or not voice.measures[0].clef_changes:
            return

        opening_clef = voice.measures[0].clef_changes[0]
        if opening_clef.offset != 0:
            return

        part.clef_sign = opening_clef.sign
        part.clef_line = opening_clef.line
        part.clef_octave_change = opening_clef.octave_change
        voice.measures[0].clef_changes.pop(0)

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
            if global_name != "global":
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
                fraction = node.fraction()
                if not fraction:
                    diagnostics.append(
                        Diagnostic(
                            code="invalid-time-signature",
                            message="Time signature has a zero denominator and was ignored.",
                            severity="error",
                            location=location_from_item(node),
                        )
                    )
                else:
                    settings.time_signature = (node.numerator(), int(1 / fraction))
            elif isinstance(node, items.KeySignature):
                pitch = node.pitch()
                settings.key_mode = node.mode() or "major"
                settings.key_fifths = self._key_fifths(pitch, settings.key_mode, flattened.transpose_specs)
            elif isinstance(node, items.Tempo):
                settings.tempo_text = self._extract_text(node.text())

        self._parse_raw_global_settings(music_node, settings, initial_state or _WalkState())
        return settings

    def _parse_raw_global_settings(self, node: items.Item, settings: _GlobalSettings, state: _WalkState) -> None:
        return self._lz._parse_raw_global_settings(node, settings, state)

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
        initial_clef: tuple[str, int, int | None] | None = None,
        initial_key_fifths: int = 0,
        initial_key_mode: str = "major",
        initial_time_signature: tuple[int, int] = (4, 4),
        out_extra_voices: list[Voice] | None = None,
    ) -> Voice:
        return self._vb.build_voice(
            voice_id=voice_id,
            source_name=source_name,
            music_node=music_node,
            measure_length=measure_length,
            assignments=assignments,
            quote_sources=quote_sources,
            diagnostics=diagnostics,
            allow_cues=allow_cues,
            initial_state=initial_state,
            initial_clef=initial_clef,
            initial_key_fifths=initial_key_fifths,
            initial_key_mode=initial_key_mode,
            initial_time_signature=initial_time_signature,
            out_extra_voices=out_extra_voices,
        )

    # ------------------------------------------------------------------
    # Linearizer delegation — all traversal and parsing logic lives in
    # ly2mxml.linearizer.Linearizer; the wrappers below keep the existing
    # call-site interface throughout the rest of this class unchanged.
    # ------------------------------------------------------------------

    def _iter_linear_nodes(self, node, state=None):
        return self._lz._iter_linear_nodes(node, state)

    def _iter_sequential_music_list(self, node, state):
        return self._lz._iter_sequential_music_list(node, state)

    def _parse_new_context(self, sequence, start_index, container_end_position):
        return self._lz._parse_new_context(sequence, start_index, container_end_position)

    def _resolve_voice_reference(self, new_context, state, assignments, sequence, start_index, container_end_position, staff_index, voice_number):
        return self._lz._resolve_voice_reference(new_context, state, assignments, sequence, start_index, container_end_position, staff_index, voice_number)

    def _voice_reference_from_node(self, node, state, assignments, next_node, container_end_position, staff_index, voice_number, context_id=None):
        return self._lz._voice_reference_from_node(node, state, assignments, next_node, container_end_position, staff_index, voice_number, context_id)

    def _iter_filtered_children(self, node, state=None):
        return self._lz._iter_filtered_children(node, state)

    def _resolve_item_reference(self, node, assignments, next_node=None, container_end_position=None):
        return self._lz._resolve_item_reference(node, assignments, next_node, container_end_position)

    def _extract_text(self, node, scheme_values=None):
        return self._lz._extract_text(node, scheme_values)

    def _raw_command_name_until(self, node, end_position):
        return self._lz._raw_command_name_until(node, end_position)

    def _duration_of_music(self, node, state=None):
        return self._lz._duration_of_music(node, state)

    def _to_pitch(self, raw_pitch, transpose_specs: tuple[_TransposeSpec, ...] = ()) -> Pitch:
        return _sr.to_pitch(raw_pitch, transpose_specs)

    def _key_fifths(self, pitch, mode: str, transpose_specs: tuple[_TransposeSpec, ...] = ()) -> int:
        return _sr.key_fifths(pitch, mode, transpose_specs)

    def _pitch_components(self, raw_pitch, transpose_specs: tuple[_TransposeSpec, ...] = ()) -> tuple[int, int, int]:
        return _sr.pitch_components(raw_pitch, transpose_specs)

    def _transpose_spec(self, from_pitch, to_pitch) -> _TransposeSpec:
        return _sr.make_transpose_spec(from_pitch, to_pitch)

    def _apply_transpose_spec(self, note: int, alter: Fraction, octave: int, spec: _TransposeSpec) -> tuple[int, Fraction, int]:
        return _sr.apply_transpose_spec(note, alter, octave, spec)

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
