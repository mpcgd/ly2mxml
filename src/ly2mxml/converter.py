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

from ly2mxml.diagnostics import Diagnostic, location_from_item
from ly2mxml.frontend.python_ly_adapter import PythonLyAdapter, SourceAnalysis
from ly2mxml.model.score import ClefChange, Direction, Lyric, Measure, MusicEvent, Part, PartCombineMode, Pitch, Score, ScoreMetadata, Voice
from ly2mxml.musicxml.writer import MusicXmlWriter
from ly2mxml.options import ExportOptions


KNOWN_BUILTIN_USER_COMMANDS = {
    "addQuote",
    "compressEmptyMeasures",
    "killCues",
    "ottava",
    "partCombine",
    "removeWithTag",
    "rf",
    "sff",
    "sffz",
    "sfpp",
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
    ".": "staccato",
    "!": "staccatissimo",
    ">": "accent",
    "-": "tenuto",
    "_": "detached-legato",
    "^": "strong-accent",
}

ORNAMENT_MAP = {
    "\\trill": "trill-mark",
    "\\mordent": "mordent",
    "\\prall": "inverted-mordent",
    "\\turn": "turn",
    "\\reverseturn": "inverted-turn",
}

FERMATA_MAP = {
    "\\fermata": "",
    "\\shortfermata": "square",
    "\\longfermata": "angled",
    "\\verylongfermata": "square",
}

TECHNICAL_MAP = {
    "\\upbow": "up-bow",
    "\\downbow": "down-bow",
    "\\stopped": "stopped",
    "\\snappizzicato": "snap-pizzicato",
    "\\open": "open-string",
    "\\flageolet": "harmonic",
    "\\thumb": "thumb-position",
}

DEFAULT_CLEF = ("G", 2, None)

CLEF_MAP = {
    "treble": DEFAULT_CLEF,
    "violin": DEFAULT_CLEF,
    "treble_8": ("G", 2, -1),
    "treble^8": ("G", 2, 1),
    "treble_15": ("G", 2, -2),
    "treble^15": ("G", 2, 2),
    "soprano": ("C", 1, None),
    "mezzosoprano": ("C", 2, None),
    "mezzo-soprano": ("C", 2, None),
    "alto": ("C", 3, None),
    "tenor": ("C", 4, None),
    "baritone": ("C", 5, None),
    "bass": ("F", 4, None),
    "bass_8": ("F", 4, -1),
    "bass^8": ("F", 4, 1),
    "bass_15": ("F", 4, -2),
    "bass^15": ("F", 4, 2),
    "percussion": ("percussion", 2, None),
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


@dataclass(slots=True)
class _GlobalSettings:
    time_signature: tuple[int, int] = (4, 4)
    key_fifths: int = 0
    key_mode: str = "major"
    tempo_text: str | None = None


@dataclass(frozen=True, slots=True)
class _WalkState:
    """Track contextual conversion state while flattening LilyPond nodes."""

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
    """Carry one flattened node together with the state needed to render it."""

    node: items.Item | _CueInsertion | _OttavaChange | _BarlineChange
    is_grace: bool
    grace_slash: bool
    scale: Fraction
    transpose_specs: tuple[_TransposeSpec, ...] = ()
    time_modification: tuple[int, int] | None = None
    tuplet_start: bool = False
    tuplet_stop: bool = False
    resolved_pitches: tuple[object, ...] = ()


@dataclass(slots=True)
class _VoiceBuildState:
    """Track measure assembly state while building one exported voice."""

    current_measure: Measure
    elapsed: Fraction = Fraction(0, 1)
    timeline_position: Fraction = Fraction(0, 1)
    current_clef: tuple[str, int, int | None] = DEFAULT_CLEF
    pending_directions: list[Direction] = field(default_factory=list)
    last_event: MusicEvent | None = None
    attachment_event: MusicEvent | None = None
    pending_tie_signature: tuple[tuple[str, int, int], ...] | None = None
    active_ottava: int | None = None


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


@dataclass(frozen=True, slots=True)
class _PartBuildContext:
    staff_index: int
    name: str | None
    short_name: str | None
    clef_sign: str
    clef_line: int
    clef_octave_change: int | None
    global_settings: _GlobalSettings


@dataclass(frozen=True, slots=True)
class _StaffPartPlan:
    part_context: _PartBuildContext
    voice_refs: tuple[_VoiceReference, ...]
    partcombine_groups: tuple[_PartCombinePlan, ...]
    lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]]


@dataclass(slots=True)
class _StaffPlanningState:
    global_ref: _VoiceReference
    voice_refs: list[_VoiceReference] = field(default_factory=list)
    partcombine_groups: list[_PartCombinePlan] = field(default_factory=list)
    lyric_sources: dict[str, list[tuple[items.Item, _WalkState]]] = field(default_factory=dict)
    last_voice_ref: _VoiceReference | None = None


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
        self._quote_voice_cache: dict[tuple[str, Fraction], Voice] = {}
        self._scheme_values_cache: dict[Path, dict[str, str]] = {}

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
        # Staff contexts are the closest LilyPond structure to exported parts,
        # so score assembly starts there and only then resolves voice planning
        # and optional partCombine grouping inside each staff.
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

    def _iter_staff_contexts(self, node: items.Item, state: _WalkState | None = None) -> Iterator[tuple[items.Context, _WalkState]]:
        """Yield each ``Staff`` context together with the state used to reach it."""

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
                resolved_clef = self._resolve_clef(node.specifier())
                if resolved_clef is None:
                    self._report_unsupported_clef(diagnostics, node, context=f"staff {staff_index}")
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

        voice = self._build_voice(
            voice_id=voice_id,
            source_name=voice_ref.name,
            music_node=voice_music,
            measure_length=part.measure_length,
            assignments=assignments,
            quote_sources=quote_sources,
            diagnostics=diagnostics,
            initial_state=voice_ref.state,
            initial_clef=(part.clef_sign, part.clef_line, part.clef_octave_change),
        )
        if not part.voices:
            self._promote_opening_voice_clef(part, voice)
        target_lyrics = lyric_sources.get(voice_ref.lyric_target, [])
        for verse_index, (lyric_source, lyric_state) in enumerate(target_lyrics, start=1):
            verse_number = verse_index if len(target_lyrics) > 1 else None
            self._apply_lyrics(voice, lyric_source, assignments, lyric_state, verse_number, diagnostics)
        part.voices.append(voice)

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
        if isinstance(node, items.Transpose):
            transposed_child = self._transposed_child_state(node, state)
            if transposed_child is not None:
                self._parse_raw_global_settings(transposed_child[0], settings, transposed_child[1])
            return

        if isinstance(node, items.MusicList):
            sequence = self._item_children(node)
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
        initial_clef: tuple[str, int, int | None] | None = None,
    ) -> Voice:
        """Flatten one LilyPond music source into a linear exported voice."""

        voice = Voice(id=voice_id, source_name=source_name)
        state = _VoiceBuildState(current_measure=Measure(number=1), current_clef=initial_clef or DEFAULT_CLEF)

        walk_state = replace(initial_state or _WalkState(), allow_cues=allow_cues, measure_length=measure_length)
        # ``_iter_linear_nodes`` resolves the nested LilyPond wrappers that can
        # affect duration, pitch interpretation, cue suppression, tag filtering,
        # and transient direction state before events are assembled into measures.
        for flattened in self._iter_linear_nodes(music_node, walk_state):
            node = flattened.node
            is_grace = flattened.is_grace
            if isinstance(node, _OttavaChange):
                state.pending_directions.extend(self._ottava_directions(node.value, state.active_ottava))
                state.active_ottava = node.value or None
            elif isinstance(node, _BarlineChange):
                style = self._barline_style(node.value)
                if style is not None:
                    self._apply_voice_barline(voice, state, style)
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
                self._add_voice_clef_change(voice, state, node, measure_length, source_name, diagnostics)
            elif isinstance(node, items.Note):
                state.attachment_event = None
                source_pitch = flattened.resolved_pitches[0] if flattened.resolved_pitches else node.pitch
                event = self._build_voice_event(
                    duration=self._duration_from_node(node.duration, flattened.scale),
                    pitches=[self._to_pitch(source_pitch, flattened.transpose_specs)],
                    flattened=flattened,
                    pending_directions=state.pending_directions,
                )
                state.pending_directions.clear()
                self._add_voice_event(voice, state, event, measure_length, source_name, diagnostics, node)
            elif isinstance(node, items.Chord):
                state.attachment_event = None
                chord_pitches = flattened.resolved_pitches or tuple(child.pitch for child in node if isinstance(child, items.Note))
                pitches = [self._to_pitch(source_pitch, flattened.transpose_specs) for source_pitch in chord_pitches]
                event = self._build_voice_event(
                    duration=self._duration_from_node(node.duration, flattened.scale),
                    pitches=pitches,
                    flattened=flattened,
                    pending_directions=state.pending_directions,
                )
                state.pending_directions.clear()
                self._add_voice_event(voice, state, event, measure_length, source_name, diagnostics, node)
            elif isinstance(node, items.Rest):
                state.attachment_event = None
                event = self._build_voice_event(
                    duration=self._duration_from_node(
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
                self._add_voice_event(voice, state, event, measure_length, source_name, diagnostics, node)
            elif isinstance(node, items.Dynamic):
                direction = self._dynamic_to_direction(str(node.token))
                if direction is None:
                    continue
                self._add_voice_direction(state, direction)
            elif isinstance(node, items.Articulation):
                target_event = self._voice_attachment_target(state)
                if target_event is None:
                    continue
                token = str(node.token)
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

        if state.current_measure.events or state.elapsed:
            state.current_measure.duration = state.elapsed
            voice.measures.append(state.current_measure)

        return voice

    def _apply_voice_barline(self, voice: Voice, state: _VoiceBuildState, style: str) -> None:
        target_measure = (
            state.current_measure
            if state.current_measure.events or state.elapsed or not voice.measures
            else voice.measures[-1]
        )
        target_measure.right_barline = style

    def _add_voice_direction(self, state: _VoiceBuildState, direction: Direction) -> None:
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

        clef_spec = self._resolve_clef(node.specifier())
        if clef_spec is None:
            self._report_unsupported_clef(diagnostics, node, context=f"voice {source_name}")
            return

        if clef_spec == state.current_clef:
            return

        clef_change = ClefChange(
            offset=state.elapsed,
            sign=clef_spec[0],
            line=clef_spec[1],
            octave_change=clef_spec[2],
        )
        if state.current_measure.clef_changes and state.current_measure.clef_changes[-1].offset == clef_change.offset:
            state.current_measure.clef_changes[-1] = clef_change
        else:
            state.current_measure.clef_changes.append(clef_change)
        state.current_clef = clef_spec

    def _finalize_voice_measure(self, voice: Voice, state: _VoiceBuildState) -> None:
        state.current_measure.duration = state.elapsed
        voice.measures.append(state.current_measure)
        state.current_measure = Measure(number=state.current_measure.number + 1)
        state.elapsed = Fraction(0, 1)
        state.last_event = None

    def _voice_attachment_target(self, state: _VoiceBuildState) -> MusicEvent | None:
        return state.last_event or state.attachment_event

    def _voice_event_signature(self, event: MusicEvent) -> tuple[tuple[str, int, int], ...] | None:
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
        if state.pending_tie_signature is not None and self._voice_event_signature(event) == state.pending_tie_signature:
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
                        message=f"Voice {source_name} exceeds the length of measure {state.current_measure.number}.",
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
            self._append_voice_rendered_event(state, slice_event, slice_duration, attach_to_event=True)
            remaining -= slice_duration
            if state.elapsed == measure_length:
                self._finalize_voice_measure(voice, state)

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

    def _build_voice_event(
        self,
        duration: Fraction,
        flattened: _FlattenedNode,
        pending_directions: list[Direction],
        pitches: list[Pitch] | None = None,
        is_rest: bool = False,
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
        }
        if pitches is not None:
            event_kwargs["pitches"] = pitches
        if is_rest:
            event_kwargs["is_rest"] = True
        return MusicEvent(**event_kwargs)

    def _iter_linear_nodes(self, node: items.Item, state: _WalkState | None = None) -> Iterable[_FlattenedNode]:
        """Flatten supported LilyPond wrappers into a linear event stream.

        This is the main traversal routine that resolves wrappers such as grace,
        transpose, tuplets, tag filters, repeats, cue insertion, and relative
        pitch context into event-ready nodes plus the state required to render
        them correctly later.
        """

        state = state or _WalkState()

        if isinstance(node, items.UserCommand):
            value = node.value()
            if isinstance(value, items.Item):
                yield from self._iter_linear_nodes(value, state)
            else:
                yield self._flattened_node(node, state)
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
            transposed_child = self._transposed_child_state(node, state)
            if transposed_child is not None:
                for flattened, _ in self._iter_linear_nodes_with_state(transposed_child[0], transposed_child[1]):
                    yield flattened
                return

        if isinstance(node, items.MusicList):
            if node.simultaneous:
                yield self._flattened_node(node, state)
                return
            yield from self._iter_sequential_music_list(node, state)
            return

        if isinstance(node, items.Scaler):
            scaled_children, child_state = self._scaled_child_items_state(node, state)
            flattened_children: list[_FlattenedNode] = []
            for child in scaled_children:
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

        filtered_children = self._filtered_node_items_state(node, state)
        if filtered_children is not None:
            for emitted_child, emitted_state in filtered_children:
                for flattened, _ in self._iter_linear_nodes_with_state(emitted_child, emitted_state):
                    yield flattened
            return

        wrapper_children = self._wrapper_child_items_state(node, state)
        if wrapper_children is not None:
            children, current_state = wrapper_children
            for child in children:
                for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                    yield flattened
            return

        if isinstance(node, items.Postfix):
            for child in node:
                if isinstance(child, items.Item):
                    for flattened, _ in self._iter_linear_nodes_with_state(child, state):
                        yield flattened
            return

        yield self._flattened_node(node, state)

    def _iter_sequential_music_list(self, node: items.MusicList, state: _WalkState) -> Iterable[_FlattenedNode]:
        """Flatten one sequential music list while preserving evolving walk state."""

        sequence = self._item_children(node)
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
                yield self._flattened_node(ottava_change[0], current_state)
                index += ottava_change[1]
                continue

            barline_change = self._parse_barline_change(sequence, index)
            if barline_change is not None:
                yield self._flattened_node(barline_change[0], current_state)
                index += barline_change[1]
                continue

            cue_request = self._parse_cue_insertion(sequence, index, current_state)
            if cue_request is not None:
                yield self._flattened_node(cue_request[0], current_state)
                index += cue_request[1]
                continue

            for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                yield flattened
            index += 1

    def _flatten_repeat(self, node: items.Repeat, state: _WalkState) -> Iterable[_FlattenedNode]:
        """Expand the repeat forms currently supported by the converter."""

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
            alternatives = self._item_children(alt) if alt else []
            if len(alternatives) == 1 and isinstance(alternatives[0], items.MusicList):
                alternatives = self._item_children(alternatives[0])
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

    def _transposed_child_state(self, node: items.Transpose, state: _WalkState) -> tuple[items.Item, _WalkState] | None:
        children = self._item_children(node)
        if len(children) < 3 or not isinstance(children[0], items.Note) or not isinstance(children[1], items.Note):
            return None
        transpose_state = replace(
            state,
            transpose_specs=state.transpose_specs + (self._transpose_spec(children[0].pitch, children[1].pitch),),
        )
        return children[2], transpose_state

    def _scaled_child_items_state(self, node: items.Scaler, state: _WalkState) -> tuple[list[items.Item], _WalkState]:
        scaled_state = replace(state, scale=state.scale * node.scaling)
        scaled_children = [
            child for child in node if isinstance(child, items.Item) and not isinstance(child, (items.Number, items.Duration))
        ]
        return scaled_children, scaled_state

    def _wrapper_child_items_state(self, node: items.Item, state: _WalkState) -> tuple[list[items.Item], _WalkState] | None:
        if isinstance(node, items.Relative):
            children = self._item_children(node)
            if not children or not isinstance(children[0], items.Note):
                return None
            return children[1:], replace(state, relative_reference=self._copy_pitch(children[0].pitch))

        if isinstance(node, items.Absolute):
            return self._item_children(node), replace(state, relative_reference=None)

        if isinstance(node, items.Postfix):
            return self._item_children(node), state

        return None

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
        sequence = self._item_children(node)
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
            tag_children = self._item_children(node)
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

    def _filtered_node_items_state(
        self,
        node: items.Item,
        state: _WalkState,
    ) -> tuple[tuple[items.Item, _WalkState], ...] | None:
        tag_result = self._consume_tag_filter([node], 0, state)
        if tag_result is None:
            return None
        return tag_result.emitted

    def _item_children(self, node: items.Item | None) -> list[items.Item]:
        if node is None:
            return []
        return [child for child in node if isinstance(child, items.Item)]

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
        """Estimate rendered duration for supported LilyPond music nodes.

        Cue insertion needs duration information before the cue voice is sliced,
        so this routine mirrors the flattening rules closely enough to preserve
        duration through supported wrappers and filters.
        """

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
            transposed_child = self._transposed_child_state(node, state)
            if transposed_child is not None:
                return self._duration_of_music(transposed_child[0], transposed_child[1])
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
            scaled_children, scaled_state = self._scaled_child_items_state(node, state)
            total = Fraction(0, 1)
            for child in scaled_children:
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

        filtered_children = self._filtered_node_items_state(node, state)
        if filtered_children is not None:
            total = Fraction(0, 1)
            for child, child_state in filtered_children:
                total += self._duration_of_music(child, child_state)
            return total

        wrapper_children = self._wrapper_child_items_state(node, state)
        if wrapper_children is not None:
            children, child_state = wrapper_children
            total = Fraction(0, 1)
            for child in children:
                total += self._duration_of_music(child, child_state)
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
        """Resolve one cue request into the slice of quote events it should emit."""

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
        diagnostics: list[Diagnostic] | None = None,
    ) -> None:
        """Attach lyric tokens to note events in score order for one voice."""

        note_events = [event for measure in voice.measures for event in measure.events if event.is_note and not event.is_grace]
        if not note_events:
            return

        lyric_tokens = list(self._iter_lyric_tokens(lyric_source, assignments, initial_state or _WalkState()))
        note_index = 0
        previous_hyphen = False
        last_lyric_event: MusicEvent | None = None
        surplus_tokens: list[_LyricToken] = []

        # LilyPond lyric streams are interpreted as a sequence of tokens aligned
        # against note events. The converter keeps this deliberately simple and
        # bounded so public support claims match only the tested workflows.
        for index, token in enumerate(lyric_tokens):
            if note_index >= len(note_events):
                surplus_tokens = lyric_tokens[index:]
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

        if diagnostics is not None:
            surplus_syllables = sum(1 for t in surplus_tokens if t.kind == "text")
            if surplus_syllables:
                verse_label = f" (verse {verse_number})" if verse_number is not None else ""
                diagnostics.append(
                    Diagnostic(
                        code="lyric-surplus",
                        message=(
                            f"Voice {voice.source_name} has {surplus_syllables} lyric syllable(s)"
                            f" with no matching note{verse_label}."
                        ),
                        severity="warning",
                    )
                )

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

    def _resolve_clef(self, clef_name: str | None) -> tuple[str, int, int | None] | None:
        if not clef_name:
            return None
        normalized = clef_name.strip().strip('"').lower().replace(" ", "")
        normalized = {
            "mezzo-soprano": "mezzosoprano",
        }.get(normalized, normalized)
        return CLEF_MAP.get(normalized)

    def _report_unsupported_clef(
        self,
        diagnostics: list[Diagnostic],
        node: items.Clef,
        *,
        context: str,
    ) -> None:
        diagnostics.append(
            Diagnostic(
                code="unsupported-clef",
                message=f"Unsupported clef in {context}: {node.specifier()}",
                severity="warning",
                location=location_from_item(node),
            )
        )

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
