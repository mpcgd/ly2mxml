\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

melody = \relative c' {
  \clef "treble"
  c4 d \clef "bass" e f |
  \clef "tenor" g4 a \clef "percussion" b c |
  \clef "treble_8" d1 |
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
