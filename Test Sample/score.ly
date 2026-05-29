% Main score file
\version "2.24.4"

\include "music.ly"

#(set-default-paper-size score-paper-size)
#(set-global-staff-size 14) % Standard size for large orchestral score

\header {
  title = \piece-title
  composer = \composer
  arranger = \arranger
}

\paper {
  #(set-paper-size score-paper-size)
  left-margin = 2\cm
  tagline = ##f
}

\score {
  \killCues
  \removeWithTag #'part
  <<
    \new StaffGroup = "Woodwinds" <<
      \new Staff \with { instrumentName = "Flûtes" shortInstrumentName = "Fl." } <<
        \clef "treble"
        \global
        \partCombine \fluteI \fluteII
      >>
      \new Staff \with { instrumentName = \markup \center-column { "Hautbois" "(ad lib.)" } shortInstrumentName = "Hb." } <<
        \clef "treble"
        \global
        \partCombine \hautboisI \hautboisII
      >>
      \new Staff \with { instrumentName = "Clarinettes" shortInstrumentName = "Cl." } <<
        \clef "treble"
        \global
        \partCombine \clarinetteI \clarinetteII
      >>
      \new Staff \with { instrumentName = "Bassons" shortInstrumentName = "Bn." } <<
        \clef "bass"
        \global
        \partCombine \bassonI \bassonII
      >>
    >>

    \new StaffGroup = "Brass" <<
      \new Staff \with { instrumentName = "Cors" shortInstrumentName = "C." } <<
        \clef "treble"
        \globalNoKey
        \partCombine \corI \corII
      >>
      \new Staff \with { instrumentName = "Trompettes" shortInstrumentName = "Tr." } <<
        \clef "treble"
        \globalNoKey
        \partCombine \trompetteI \trompetteII
      >>
      \new Staff \with { instrumentName = \markup \center-column { "Trombones" "I & II" } shortInstrumentName = "Trb. 1-2" } <<
        \clef "bass"
        \global
        \partCombine \tromboneI \tromboneII
      >>
      \new Staff \with { instrumentName = "Trombone III" shortInstrumentName = "Trb. 3" } <<
        \clef "bass"
        \global
        \tromboneIII
      >>
      \new Staff \with { instrumentName = "Serpent" shortInstrumentName = "Serp." } <<
        \clef "bass"
        \global
        \serpent
      >>
    >>

    \new StaffGroup = "Strings" <<
      \new Staff \with { instrumentName = \markup \center-column { "Violons I" "(ad lib.)" } shortInstrumentName = "Vln. I" } <<
        \clef "treble"
        \global
        \violonI
      >>
      \new Staff \with { instrumentName = \markup \center-column { "Violons II" "(ad lib.)" } shortInstrumentName = "Vln. II" } <<
        \clef "treble"
        \global
        \violonII
      >>
      \new Staff \with { instrumentName = \markup \center-column { "Altos" "(ad lib.)" } shortInstrumentName = "Alt." } <<
        \clef "alto"
        \global
        \alto
      >>
      \new Staff \with { instrumentName = \markup \center-column { "Violoncelles" "(ad lib.)" } shortInstrumentName = "Vlc." } <<
        \clef "bass"
        \global
        \violoncelle
      >>
      \new Staff \with { instrumentName = \markup \center-column { "Contrebasses" "(ad lib.)" } shortInstrumentName = "Cb." } <<
        \clef "bass"
        \global
        \contrebasse
      >>
    >>
  >>
  \layout {
    \context {
      \Staff
      \RemoveEmptyStaves
    }
  }
}

% MIDI output
\score {
  \unfoldRepeats {
    <<
      \new Staff \with { instrumentName = "Flûte 1" midiInstrument = "flute" } { \global \fluteI }
      \new Staff \with { instrumentName = "Flûte 2" midiInstrument = "flute" } { \global \fluteII }
      \new Staff \with { instrumentName = "Hautbois 1" midiInstrument = "oboe" } { \global \hautboisI }
      \new Staff \with { instrumentName = "Hautbois 2" midiInstrument = "oboe" } { \global \hautboisII }
      \new Staff \with { instrumentName = "Clarinette 1" midiInstrument = "clarinet" } { \global \clarinetteI }
      \new Staff \with { instrumentName = "Clarinette 2" midiInstrument = "clarinet" } { \global \clarinetteII }
      \new Staff \with { instrumentName = "Basson 1" midiInstrument = "bassoon" } { \global \bassonI }
      \new Staff \with { instrumentName = "Basson 2" midiInstrument = "bassoon" } { \global \bassonII }
      \new Staff \with { instrumentName = "Cor 1" midiInstrument = "french horn" } { \globalNoKey \corI }
      \new Staff \with { instrumentName = "Cor 2" midiInstrument = "french horn" } { \globalNoKey \corII }
      \new Staff \with { instrumentName = "Trompette 1" midiInstrument = "trumpet" } { \globalNoKey \trompetteI }
      \new Staff \with { instrumentName = "Trompette 2" midiInstrument = "trumpet" } { \globalNoKey \trompetteII }
      \new Staff \with { instrumentName = "Trombone 1" midiInstrument = "trombone" } { \global \tromboneI }
      \new Staff \with { instrumentName = "Trombone 2" midiInstrument = "trombone" } { \global \tromboneII }
      \new Staff \with { instrumentName = "Trombone 3" midiInstrument = "trombone" } { \global \tromboneIII }
      \new Staff \with { instrumentName = "Serpent" midiInstrument = "tuba" } { \global \serpent }
      \new Staff \with { instrumentName = "Violon 1" midiInstrument = "violin" } { \global \violonI }
      \new Staff \with { instrumentName = "Violon 2" midiInstrument = "violin" } { \global \violonII }
      \new Staff \with { instrumentName = "Alto" midiInstrument = "viola" } { \global \alto }
      \new Staff \with { instrumentName = "Violoncelle" midiInstrument = "cello" } { \global \violoncelle }
      \new Staff \with { instrumentName = "Contrebasse" midiInstrument = "contrabass" } { \global \contrebasse }
    >>
  }
  \midi {
    \tempo 4 = 100
  }
}
