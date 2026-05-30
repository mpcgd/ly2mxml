\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = \relative c' {
  \repeat tremolo 4 { c16 }
  \repeat tremolo 4 { d16 e16 }
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
