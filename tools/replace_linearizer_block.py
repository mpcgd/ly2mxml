import sys

THIN_WRAPPERS = '''        return MusicEvent(**event_kwargs)

    # -----------------------------------------------------------------
    # Linearizer delegation — all traversal and parsing logic lives in
    # ly2mxml.linearizer.Linearizer; the wrappers below keep the existing
    # call-site interface throughout the rest of this class unchanged.
    # -----------------------------------------------------------------

    def _iter_linear_nodes(self, node, state=None):
        return self._lz._iter_linear_nodes(node, state)

    def _iter_sequential_music_list(self, node, state):
        return self._lz._iter_sequential_music_list(node, state)

    def _flatten_repeat(self, node, state):
        return self._lz._flatten_repeat(node, state)

    def _flatten_tremolo(self, node, body, repeat_count, state):
        return self._lz._flatten_tremolo(node, body, repeat_count, state)

    def _iter_linear_nodes_with_state(self, node, state):
        return self._lz._iter_linear_nodes_with_state(node, state)

    def _flattened_node(self, node, state):
        return self._lz._flattened_node(node, state)

    def _advance_relative_state(self, state, flattened):
        return self._lz._iter_linear_nodes_with_state  # not called directly; kept for compat
        # (advance_relative_state is internal to Linearizer)

    def _resolve_relative_pitch(self, raw_pitch, reference_pitch):
        return _sr.resolve_relative_pitch(raw_pitch, reference_pitch)

    def _resolve_relative_chord(self, node, reference_pitch):
        return _sr.resolve_relative_chord(node, reference_pitch)

    def _copy_pitch(self, raw_pitch):
        return _sr.copy_pitch(raw_pitch)

    def _transposed_child_state(self, node, state):
        return self._lz._transposed_child_state(node, state)

    def _scaled_child_items_state(self, node, state):
        return self._lz._scaled_child_items_state(node, state)

    def _wrapper_child_items_state(self, node, state):
        return self._lz._wrapper_child_items_state(node, state)

    def _parse_barline_change(self, sequence, start_index):
        return self._lz._parse_barline_change(sequence, start_index)

    def _parse_rehearsal_mark(self, sequence, start_index):
        return self._lz._parse_rehearsal_mark(sequence, start_index)

    def _parse_cue_insertion(self, sequence, start_index, state):
        return self._lz._parse_cue_insertion(sequence, start_index, state)

    def _parse_ottava_change(self, sequence, start_index):
        return self._lz._parse_ottava_change(sequence, start_index)

    def _raw_command_name(self, node, next_node):
        return self._lz._raw_command_name(node, next_node)

    def _raw_command_name_until(self, node, end_position):
        return self._lz._raw_command_name_until(node, end_position)

    def _source_span(self, item, end_position):
        return self._lz._source_span(item, end_position)

    def _parse_new_context(self, sequence, start_index, container_end_position):
        return self._lz._parse_new_context(sequence, start_index, container_end_position)

    def _resolve_voice_reference(self, new_context, state, assignments, sequence, start_index, container_end_position, staff_index, voice_number):
        return self._lz._resolve_voice_reference(new_context, state, assignments, sequence, start_index, container_end_position, staff_index, voice_number)

    def _voice_reference_from_node(self, node, state, assignments, next_node, container_end_position, staff_index, voice_number, context_id=None):
        return self._lz._voice_reference_from_node(node, state, assignments, next_node, container_end_position, staff_index, voice_number, context_id)

    def _source_text_for_item(self, item):
        return self._lz._source_text_for_item(item)

    def _iter_filtered_children(self, node, state=None):
        return self._lz._iter_filtered_children(node, state)

    def _consume_tag_filter(self, sequence, start_index, state):
        return self._lz._consume_tag_filter(sequence, start_index, state)

    def _filtered_node_items_state(self, node, state):
        return self._lz._filtered_node_items_state(node, state)

    def _item_children(self, node):
        return self._lz._item_children(node)

    def _state_with_removed_tag(self, state, tag_name):
        return self._lz._state_with_removed_tag(state, tag_name)

    def _state_with_removed_tags(self, state, tag_names):
        return self._lz._state_with_removed_tags(state, tag_names)

    def _state_with_keep_tags(self, state, tag_names):
        return self._lz._state_with_keep_tags(state, tag_names)

    def _extract_tag_name(self, node):
        return self._lz._extract_tag_name(node)

    def _extract_tag_names(self, node):
        return self._lz._extract_tag_names(node)

    def _collect_scheme_tag_names(self, node, names):
        return self._lz._collect_scheme_tag_names(node, names)

    def _duration_of_music(self, node, state=None):
        return self._lz._duration_of_music(node, state)

    def _resolve_item_reference(self, node, assignments, next_node=None, container_end_position=None):
        return self._lz._resolve_item_reference(node, assignments, next_node, container_end_position)

    def _extract_scheme_int(self, node):
        return self._lz._extract_scheme_int(node)

    def _extract_text(self, node, scheme_values=None):
        return self._lz._extract_text(node, scheme_values)

    def _duration_from_node(self, raw_duration, scale=None, token=None, measure_length=None):
        from fractions import Fraction
        return self._lz._duration_from_node(raw_duration, scale if scale is not None else Fraction(1, 1), token, measure_length)

    def _time_modification_for_scaler(self, node):
        return self._lz._time_modification_for_scaler(node)
'''

with open(r"c:\_Privat\Ly2Mxml\src\ly2mxml\converter.py", "r", encoding="utf-8") as f:
    src = f.read()

START_MARKER = "        return MusicEvent(**event_kwargs)\n\n    def _iter_linear_nodes("
END_MARKER = "\n    def _to_pitch(self, raw_pitch, transpose_specs: tuple[_TransposeSpec, ...] = ()) -> Pitch:"

start_idx = src.find(START_MARKER)
end_idx = src.find(END_MARKER)
if start_idx == -1 or end_idx == -1:
    print(f"MARKERS NOT FOUND: start={start_idx}, end={end_idx}")
    sys.exit(1)

# Keep what comes after the end marker
after = src[end_idx:]

new_src = src[:start_idx] + THIN_WRAPPERS + after

with open(r"c:\_Privat\Ly2Mxml\src\ly2mxml\converter.py", "w", encoding="utf-8") as f:
    f.write(new_src)

print(f"Replaced block: {end_idx - start_idx} chars -> {len(THIN_WRAPPERS)} chars")
print("Done")
