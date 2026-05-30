\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = { c'4\naturalHarmonic d'4\artificialHarmonic e'4 f'4 }

\score {
  \new Staff <<
    \global
    \melody
  >>
}
