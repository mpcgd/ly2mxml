"""AST traversal and flattening for the LilyPond converter pipeline.

The ``Linearizer`` class converts nested python-ly AST nodes into a flat stream
of ``_FlattenedNode`` objects ready for the voice-building phase.  It is
stateless except for a source-text cache (used to extract raw source spans for
context-command detection) and the export options.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import re
from typing import Iterable

from ly.music import items

from ly2mxml._types import (
    _BarlineChange,
    _CueInsertion,
    _FlattenedNode,
    _GlobalSettings,
    _NewContextCommand,
    _OttavaChange,
    _PartialDuration,
    _RehearsalMark,
    _SecondaryVoiceBlocks,
    _SequenceFilterResult,
    _TransposeSpec,
    _VoiceReference,
    _WalkState,
)
from ly2mxml.diagnostics import location_from_item
from ly2mxml.options import ExportOptions
from ly2mxml import state_resolver as _sr

# ---------------------------------------------------------------------------
# Module-level constants (previously in converter.py)
# ---------------------------------------------------------------------------

MUSICAL_NODE_TYPES = (items.Note, items.Rest, items.Chord)

NEW_CONTEXT_PATTERN = re.compile(r'\\new\s+([A-Za-z]+)(?:\s*=\s*"([^"]+)")?\s*$')
UNRESOLVED_COMMAND_PATTERN = re.compile(r"\\+([A-Za-z]+)\b")


class Linearizer:
    """Flatten python-ly AST nodes into a linear stream of ``_FlattenedNode`` objects.

    Parameters
    ----------
    loader:
        An object with a ``read_text(path)`` method (``PythonLyAdapter.loader``).
    source_text_cache:
        Shared mutable dict owned by the converter; avoids re-reading files.
    export_options:
        Controls cue-note inclusion and other converter behaviour.
    """

    def __init__(
        self,
        loader,
        source_text_cache: dict[Path, str],
        export_options: ExportOptions,
    ) -> None:
        self.loader = loader
        self._source_text_cache = source_text_cache
        self.export_options = export_options

    # ------------------------------------------------------------------
    # Public traversal entry points
    # ------------------------------------------------------------------

    def _iter_linear_nodes(self, node: items.Item, state: _WalkState | None = None) -> Iterable[_FlattenedNode]:
        """Flatten supported LilyPond wrappers into a linear event stream."""

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
            grace_slash = _sr.grace_has_slash(node)
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
                sub_blocks = self._split_voice_separator_block(node)
                if sub_blocks is not None and len(sub_blocks) >= 2:
                    yield from self._iter_sequential_music_list(sub_blocks[0], state)
                    marker = _SecondaryVoiceBlocks(
                        blocks=tuple(sub_blocks[1:]),
                        walk_state=state,
                        source_node=node,
                    )
                    yield self._flattened_node(marker, state)
                else:
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

            rehearsal_mark = self._parse_rehearsal_mark(sequence, index)
            if rehearsal_mark is not None:
                yield self._flattened_node(rehearsal_mark[0], current_state)
                index += rehearsal_mark[1]
                continue

            cue_request = self._parse_cue_insertion(sequence, index, current_state)
            if cue_request is not None:
                yield self._flattened_node(cue_request[0], current_state)
                index += cue_request[1]
                continue

            if isinstance(child, items.TimeSignature):
                fraction = child.fraction()
                if fraction:
                    new_length = Fraction(child.numerator(), int(1 / fraction))
                    current_state = replace(current_state, measure_length=new_length)

            if isinstance(child, items.Partial):
                partial_len = child.partial_length()
                if partial_len:
                    current_state = replace(current_state, measure_length=partial_len)
                    yield self._flattened_node(_PartialDuration(duration=partial_len, source_node=child), current_state)
                    index += 1
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

        if specifier == "tremolo":
            yield from self._flatten_tremolo(node, body, repeat_count, state)
            return

        yield self._flattened_node(node, state)

    def _flatten_tremolo(
        self,
        node: items.Repeat,
        body: list[items.Item],
        repeat_count: int,
        state: _WalkState,
    ) -> Iterable[_FlattenedNode]:
        """Expand a tremolo repeat into scaled musical events with tremolo marks."""

        import math

        if repeat_count > 0 and (repeat_count & (repeat_count - 1)) == 0:
            slash_count = int(math.log2(repeat_count))
        else:
            slash_count = max(1, round(math.log2(repeat_count))) if repeat_count > 0 else 1

        scaled_state = replace(state, scale=state.scale * repeat_count)
        body_flattened: list[_FlattenedNode] = []
        current_state = scaled_state
        for child in body:
            if isinstance(child, items.Item):
                for flattened, current_state in self._iter_linear_nodes_with_state(child, current_state):
                    body_flattened.append(flattened)

        musical_indices = [
            i for i, f in enumerate(body_flattened) if isinstance(f.node, MUSICAL_NODE_TYPES)
        ]

        if len(musical_indices) == 1:
            body_flattened[musical_indices[0]].tremolo_type = "single"
            body_flattened[musical_indices[0]].tremolo_slashes = slash_count
        elif len(musical_indices) >= 2:
            body_flattened[musical_indices[0]].tremolo_type = "start"
            body_flattened[musical_indices[0]].tremolo_slashes = slash_count
            body_flattened[musical_indices[-1]].tremolo_type = "stop"
            body_flattened[musical_indices[-1]].tremolo_slashes = slash_count

        yield from body_flattened

    def _iter_linear_nodes_with_state(self, node: items.Item, state: _WalkState) -> Iterable[tuple[_FlattenedNode, _WalkState]]:
        current_state = state
        for flattened in self._iter_linear_nodes(node, current_state):
            current_state = _sr.advance_relative_state(current_state, flattened)
            yield flattened, current_state

    def _flattened_node(
        self,
        node: items.Item | _CueInsertion | _OttavaChange | _BarlineChange | _RehearsalMark | _PartialDuration | _SecondaryVoiceBlocks,
        state: _WalkState,
    ) -> _FlattenedNode:
        flattened = _FlattenedNode(
            node=node,
            is_grace=state.is_grace,
            grace_slash=state.grace_slash,
            scale=state.scale,
            transpose_specs=state.transpose_specs,
        )
        if isinstance(node, items.Note):
            flattened.resolved_pitches = (_sr.resolve_relative_pitch(node.pitch, state.relative_reference),)
        elif isinstance(node, items.Chord):
            flattened.resolved_pitches = _sr.resolve_relative_chord(node, state.relative_reference)
        return flattened

    # ------------------------------------------------------------------
    # Child / wrapper helpers
    # ------------------------------------------------------------------

    def _transposed_child_state(self, node: items.Transpose, state: _WalkState) -> tuple[items.Item, _WalkState] | None:
        children = self._item_children(node)
        if len(children) < 3 or not isinstance(children[0], items.Note) or not isinstance(children[1], items.Note):
            return None
        transpose_state = replace(
            state,
            transpose_specs=state.transpose_specs + (_sr.make_transpose_spec(children[0].pitch, children[1].pitch),),
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
            return children[1:], replace(state, relative_reference=_sr.copy_pitch(children[0].pitch))

        if isinstance(node, items.Absolute):
            return self._item_children(node), replace(state, relative_reference=None)

        if isinstance(node, items.Postfix):
            return self._item_children(node), state

        return None

    def _split_voice_separator_block(
        self,
        music_list: items.MusicList,
    ) -> list[items.MusicList] | None:
        """Return the sequential sub-blocks of a << { } \\\\ { } >> shorthand block."""

        sub_blocks: list[items.MusicList] = []
        for child in music_list:
            if isinstance(child, items.Context):
                return None
            if isinstance(child, items.VoiceSeparator):
                continue
            if isinstance(child, items.MusicList) and not child.simultaneous:
                sub_blocks.append(child)
        return sub_blocks if len(sub_blocks) >= 2 else None

    # ------------------------------------------------------------------
    # Tag filtering
    # ------------------------------------------------------------------

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
            tag_names = self._extract_tag_names(tag_children[0] if tag_children else None)
            if command_name == "removeWithTag":
                content_nodes = tuple(
                    (child, self._state_with_removed_tags(state, tag_names))
                    for child in tag_children[1:]
                )
                return _SequenceFilterResult(emitted=content_nodes, remaining_state=state, consumed=1)
            if command_name == "keepWithTag":
                content_nodes = tuple(
                    (child, self._state_with_keep_tags(state, tag_names))
                    for child in tag_children[1:]
                )
                return _SequenceFilterResult(emitted=content_nodes, remaining_state=state, consumed=1)
            if command_name == "tag":
                if tag_names & state.removed_tags:
                    return _SequenceFilterResult(emitted=(), remaining_state=state, consumed=1)
                if state.keep_tags and not (tag_names & state.keep_tags):
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
            tag_names = self._extract_tag_names(next_node)
            if not tag_names:
                return None
            return _SequenceFilterResult(
                emitted=(),
                remaining_state=self._state_with_removed_tags(state, tag_names),
                consumed=2,
            )

        if command_name == "keepWithTag":
            tag_names = self._extract_tag_names(next_node)
            if not tag_names:
                return None
            return _SequenceFilterResult(
                emitted=(),
                remaining_state=self._state_with_keep_tags(state, tag_names),
                consumed=2,
            )

        if command_name == "tag":
            tag_names = self._extract_tag_names(next_node)
            content_node = sequence[start_index + 2] if start_index + 2 < len(sequence) else None
            if not tag_names or not isinstance(content_node, items.Item):
                return None
            if tag_names & state.removed_tags:
                return _SequenceFilterResult(emitted=(), remaining_state=state, consumed=3)
            if state.keep_tags and not (tag_names & state.keep_tags):
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

    def _state_with_removed_tag(self, state: _WalkState, tag_name: str | None) -> _WalkState:
        if not tag_name:
            return state
        return replace(state, removed_tags=state.removed_tags | frozenset({tag_name}))

    def _state_with_removed_tags(self, state: _WalkState, tag_names: frozenset[str]) -> _WalkState:
        if not tag_names:
            return state
        return replace(state, removed_tags=state.removed_tags | tag_names)

    def _state_with_keep_tags(self, state: _WalkState, tag_names: frozenset[str]) -> _WalkState:
        if not tag_names:
            return state
        return replace(state, keep_tags=state.keep_tags | tag_names)

    def _extract_tag_name(self, node: items.Item | None) -> str | None:
        names = self._extract_tag_names(node)
        return next(iter(names), None)

    def _extract_tag_names(self, node: items.Item | None) -> frozenset[str]:
        """Return all tag names from a tag argument (single or Scheme list form)."""

        if node is None:
            return frozenset()
        if isinstance(node, items.String):
            v = node.value()
            return frozenset({v}) if v else frozenset()
        if isinstance(node, items.Scheme):
            names: set[str] = set()
            self._collect_scheme_tag_names(node, names)
            return frozenset(names)
        names: set[str] = set()
        for child in node:
            if isinstance(child, items.Item):
                names |= self._extract_tag_names(child)
        if not names and type(node).__name__ == "SchemeItem":
            return frozenset({str(node.token)})
        return frozenset(names)

    def _collect_scheme_tag_names(self, node: object, names: set[str]) -> None:
        """Recursively collect all SchemeItem token strings into names."""

        if type(node).__name__ == "SchemeItem":
            names.add(str(getattr(node, "token", "")))
        else:
            for child in node:
                self._collect_scheme_tag_names(child, names)

    # ------------------------------------------------------------------
    # Sequential event parsers (barline, rehearsal mark, cue, ottava)
    # ------------------------------------------------------------------

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

    def _parse_rehearsal_mark(
        self,
        sequence: list[items.Item],
        start_index: int,
    ) -> tuple[_RehearsalMark, int] | None:
        node = sequence[start_index]
        if not isinstance(node, items.Command) or str(node.token) != "\\mark":
            return None

        next_node = sequence[start_index + 1] if start_index + 1 < len(sequence) else None

        scheme_int = self._extract_scheme_int(next_node)
        if scheme_int is not None:
            return _RehearsalMark(label=str(scheme_int), source_node=node), 2

        if isinstance(next_node, items.String):
            text = next_node.value()
            if text:
                return _RehearsalMark(label=text, source_node=node), 2

        consumed = 2 if (isinstance(next_node, items.Command) and str(next_node.token) == "\\default") else 1
        return _RehearsalMark(label=None, source_node=node), consumed

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

    # ------------------------------------------------------------------
    # Context / voice-reference parsing (used by staff planning)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Duration estimation
    # ------------------------------------------------------------------

    def _duration_of_music(self, node: items.Item, state: _WalkState | None = None) -> Fraction:
        """Estimate rendered duration for supported LilyPond music nodes."""

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

    def _time_modification_for_scaler(self, node: items.Scaler) -> tuple[int, int]:
        token = str(getattr(node, "token", ""))
        if token == "\\tuplet":
            return node.numerator, node.denominator
        return node.denominator, node.numerator

    # ------------------------------------------------------------------
    # Raw source text helpers
    # ------------------------------------------------------------------

    def _source_text_for_item(self, item: object) -> str | None:
        location = location_from_item(item)
        if location.file_path is None:
            return None
        source_text = self._source_text_cache.get(location.file_path)
        if source_text is None:
            source_text = self.loader.read_text(location.file_path)
            self._source_text_cache[location.file_path] = source_text
        return source_text

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

    # ------------------------------------------------------------------
    # Text / scheme extraction
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _item_children(self, node: items.Item | None) -> list[items.Item]:
        if node is None:
            return []
        return [child for child in node if isinstance(child, items.Item)]

    # ------------------------------------------------------------------
    # Global-settings extraction
    # ------------------------------------------------------------------

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
                    command_name = self._raw_command_name_until(
                        child,
                        getattr(next_node, "position", None) if next_node is not None else None,
                    )
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
                        settings.key_fifths = _sr.key_fifths(next_node.pitch, settings.key_mode, state.transpose_specs)
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
