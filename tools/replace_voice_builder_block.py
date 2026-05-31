"""Replace _build_voice and all voice-helper method bodies in converter.py
with a single thin wrapper that delegates to self._vb.build_voice().
"""
import re
from pathlib import Path

CONVERTER = Path(__file__).parent.parent / "src" / "ly2mxml" / "converter.py"

src = CONVERTER.read_text(encoding="utf-8")

# The block to replace starts at "    def _build_voice(" and ends just before
# "    def _to_pitch(".  We detect both markers precisely.

START_MARKER = "    def _build_voice(\n"
END_MARKER = "\n    def _to_pitch("

start_idx = src.index(START_MARKER)
end_idx = src.index(END_MARKER)

old_block = src[start_idx:end_idx]
print(f"Replacing block: {len(old_block)} chars")

NEW_BLOCK = '''\
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
'''

new_src = src[:start_idx] + NEW_BLOCK + src[end_idx:]
CONVERTER.write_text(new_src, encoding="utf-8")
print(f"New block: {len(NEW_BLOCK)} chars")
print("Done")
