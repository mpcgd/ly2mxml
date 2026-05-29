\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

melody = \relative c' {
  c4\< d e\! f
  \tuplet 3/2 { g8 a b } c4 d4 e4
  \times 2/3 { d4 e f } g4 a4
  \scaleDurations 2/3 { a4 b c } d4 e4
  \repeat unfold 2 { e8 f } g4 a4 b4
  \repeat volta 2 { b4 c } \alternative { { d4 e } { f4 g } }
}

\score {
  \new Staff <<
    \clef "treble"
    \global
    \melody
  >>
}