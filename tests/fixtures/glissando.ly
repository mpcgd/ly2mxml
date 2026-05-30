\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = { c'2\glissando d'2 e'2\glissando f'2 }

\score {
  \new Staff <<
    \global
    \melody
  >>
}
