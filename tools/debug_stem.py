"""Debug stem direction dispatch in _build_voice."""
from pathlib import Path
from ly.music import items
from ly2mxml.converter import LilypondConverter, _WalkState, _VoiceBuildState, VOICE_COMMAND_STEMS
from fractions import Fraction

orig_bv = LilypondConverter._build_voice


def traced_bv(
    self, voice_id, source_name, music_node, measure_length,
    assignments, quote_sources, diagnostics,
    allow_cues=True, initial_state=None, initial_clef=None,
    initial_key_fifths=0, initial_key_mode="major",
    initial_time_signature=(4, 4), out_extra_voices=None,
):
    print(f"build_voice({source_name!r}), music_node={type(music_node).__name__}")
    walk = _WalkState(measure_length=measure_length)
    for i, fn in enumerate(self._iter_linear_nodes(music_node, walk)):
        tok = str(getattr(fn.node, "token", ""))
        print(f"  [{i}] {type(fn.node).__name__} {tok!r}")
        if i > 14:
            break
    return orig_bv(
        self, voice_id, source_name, music_node, measure_length,
        assignments, quote_sources, diagnostics,
        allow_cues, initial_state, initial_clef, initial_key_fifths,
        initial_key_mode, initial_time_signature, out_extra_voices,
    )


LilypondConverter._build_voice = traced_bv
score = LilypondConverter().build_score(
    Path(r"c:\_Privat\Ly2Mxml\tests\fixtures\stem_direction.ly")
)
for p in score.parts:
    for v in p.voices:
        for m in v.measures:
            for e in m.events:
                if e.pitches:
                    print(f"note {e.pitches[0].step} stem={e.stem!r}")
