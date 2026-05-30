# LilyPond Syntax Support

This page documents the current LilyPond surface implemented by `ly2mxml`. The project intentionally supports a bounded, test-backed subset of LilyPond syntax rather than claiming full LilyPond compatibility.

Use the sections below as the support contract:

- **Implemented** means the syntax is handled in the converter and backed by current tests and fixtures.
- **Implemented but bounded** means the syntax works only in the documented forms and should not be described more broadly.
- **Not yet implemented / unsupported** means the syntax is currently outside the supported conversion surface.

## Implemented

### Core music representation

- notes
- rests
- chords
- relative pitch with `\relative`
- transposed music with `\transpose`
- key signatures with `\key`
- time signatures with `\time`
- opening staff clef extraction and mid-staff clef changes via `\clef "name"` inside a voice stream
- spacer rests with `s` (e.g. `s4`) and `\skip`
- pickup / anacrusis measure with `\partial`

### Structural expansion and duration handling

- `\repeat unfold`
- `\repeat volta`
- `\repeat tremolo` (single-note and two-note forms)
- `\tuplet`
- `\times`
- `\scaleDurations`

### Expression and notation

- slurs
- ties
- grace notes, including bounded appoggiatura/acciaccatura slash handling
- supported dynamic commands: `\ppp`, `\pppp`, `\pp`, `\p`, `\mp`, `\mf`, `\f`, `\ff`, `\fff`, `\ffff`, `\fp`, `\fz`, `\rf`, `\rfz`, `\sf`, `\sfp`, `\sfpp`, `\sfz`, `\sff`, `\sffz`
- text dynamics `\cresc`, `\dim`, `\decresc`
- wedge commands `\<`, `\>`, and `\!`
- supported articulation spellings: staccato (`-.`, `.`, `\staccato`), staccatissimo (`-!`, `\staccatissimo`), accent (`->`, `>`, `\accent`), tenuto (`--`, `\tenuto`), detached-legato (`-_`, `\portato`), strong-accent (`-^`, `^`, `\marcato`), soft-accent (`\espressivo`)
- ornaments: `\trill`, `\mordent`, `\prall`, `\turn`, `\reverseturn`, `\prallmordent`, `\prallprall`, `\downmordent`, `\upmordent`, `\tremblement`, `\haydn`
- fermata variants: `\fermata`, `\shortfermata`, `\longfermata`, `\verylongfermata`
- technical notations: `\upbow`, `\downbow`, `\stopped`, `\open`, `\flageolet`, `\snappizzicato`, `\thumb`, `\lheel`, `\rheel`, `\ltoe`, `\rtoe`, `\naturalHarmonic`, `\artificialHarmonic`
- explicit barlines with `\bar` including repeat barlines (`\|:`, `:|`), double barline (`||`), final barline (`|.`), dotted, dashed, short, tick, and invisible forms
- `\ottava`
- `\arpeggio`
- `\glissando` (start/stop pair on successive notes)
- phrasing slurs (`\(` … `\)` and `items.PhrasingSlur`)
- stem direction commands: `\voiceOne`, `\voiceTwo`, `\voiceThree`, `\voiceFour`, `\stemUp`, `\stemDown`, `\stemNeutral`, `\oneVoice`
- rehearsal marks: `\coda`, `\segno` (exported as MusicXML `<coda>` and `<segno>` direction types)
- performance text marks: `\arco`, `\pizzicato`, `\colLegno`, `\sulTasto`, `\sulPonticello` (exported as `<words>` directions)

### Parts, voices, and assembly

- `\partCombine` planning and export
- export of partCombine groups as either separate parts or one combined MusicXML part
- staff group brackets via `\new StaffGroup`, `\new ChoirStaff`, `\new GrandStaff`, and `\new PianoStaff` (bracket or brace in MusicXML)
- `\include`
- user-variable assignment resolution
- mid-stream polyphony: `<< {v1} \\ {v2} >>` blocks embedded inside a sequential voice variable are split into multiple parallel MusicXML voices

### Quotes and cues

- `\addQuote`
- `\cueDuring`
- `\quoteDuring`
- `\killCues`
- cue export ignored by default
- cue export when enabled explicitly
- cue-duration traversal through currently tested wrappers such as `\transpose`, `\scaleDurations`, `\relative`, and `\tag`

### Lyrics

- `\addlyrics`
- bounded `\lyricsto` support in the currently tested named-voice forms
- multiple lyric verses in the currently tested forms

### Tag filtering and measure-rest handling

- bounded `\tag` handling including multi-name tag lists
- bounded `\removeWithTag` handling
- `\keepWithTag` for tag-based content selection
- `\compressEmptyMeasures`
- uppercase measure-rest duration semantics such as `R1*10`
- MusicXML multiple-rest export for supported consecutive full-measure rests

## Implemented But Bounded

### Clefs

- Initial staff clefs and mid-staff clef changes are supported for the converter's current common MusicXML-mappable clef set.
- The currently mapped set includes treble, bass, alto, tenor, soprano, mezzosoprano, baritone, percussion, and the supported `*_8`, `*_15`, `^8`, and `^15` octave variants covered by the converter.
- Do not assume arbitrary LilyPond clef aliases or conflicting clef-change schedules across multiple rendered voices in one staff.

### Repeats

- Repeat support covers `\repeat unfold`, `\repeat volta`, and `\repeat tremolo`.
- Other repeat forms should not be described as supported.

### Cues

- Cue support is quote-based and depends on `\addQuote` plus `\cueDuring` or `\quoteDuring`.
- The converter preserves duration for the currently tested wrapper forms, but public docs should not imply arbitrary cue extraction or styling support.

### Lyrics

- Lyrics support covers `\addlyrics`, `\lyricsto` in named-voice variable form, and `\lyricsto` in inline block form (`\new Lyrics { \lyricsto "voice" { words } }`).
- Multiple lyric verses are supported in the currently tested forms.
- Do not describe the project as supporting LilyPond lyrics generically.

### Tags

- Tag filtering supports the tested `\tag`, `\removeWithTag`, and `\keepWithTag` forms, including multi-name tag lists with Scheme list syntax.
- Avoid claiming broad nested tag semantics beyond those forms.

### PartCombine

- PartCombine support is limited to the converter's current two-mode export model.
- The documentation should not claim full LilyPond engraving-equivalent partCombine behavior.

### Dynamics, articulations, and Scheme

- Document only the current mapped dynamic and articulation forms listed above.
- Additional LilyPond dynamic or articulation commands beyond those listed are not handled.
- Scheme support is bounded to parsing and lookup behavior used by the converter, not arbitrary Scheme evaluation.

### Barlines and tempo

- Barline support covers `\bar` with the following mapped forms: repeat start (`\|:` / `|:`), repeat end (`:|`), light-light (`||`), light-heavy (`|.`), heavy-heavy (`.|.`), dotted (`:.`), dashed (`-`), short (`!`), tick (`'`), and invisible (`""`). Repeat barlines include MusicXML `<repeat>` directives with direction.
- Tempo handling should be described carefully from the current output behavior rather than as a generic playback feature promise.

## Not Yet Implemented / Unsupported

- repeat forms beyond `\repeat unfold`, `\repeat volta`, and `\repeat tremolo`
- context-override clef scheduling (`\override Staff.Clef`); only `\clef "name"` inside a voice stream is supported
- general Scheme-driven music evaluation or arbitrary Scheme execution semantics
- unknown LilyPond commands outside the currently handled command set
- broader lyric constructs beyond the currently tested `\addlyrics` and `\lyricsto` forms
- broader cue constructs beyond quote-based cue extraction from `\addQuote` sources
- broader tag semantics beyond the currently tested `\tag`, `\removeWithTag`, and `\keepWithTag` forms

## Areas Where Docs Should Stay Conservative

- complex nested tag interactions
- more intricate cue-duration mismatch cases than the current fixtures cover
- combined `\partCombine` export mixed with more complex cue or direction interaction than the current tests cover
- grace-note edge cases mixed with denser slur, tie, or articulation combinations than the current fixtures exercise
- LilyPond syntax that may parse under `python-ly` but is not explicitly handled and tested in `ly2mxml`

## How To Extend This Matrix

When adding support for a new LilyPond construct:

1. add or extend converter logic
2. add focused fixtures and tests
3. update this matrix

If a construct is not test-backed, it should remain in the bounded or unsupported sections.