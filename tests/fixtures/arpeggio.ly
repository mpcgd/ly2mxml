\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = { <c' e' g'>1\arpeggio }

\score {
  \new Staff <<
    \global
    \melody
  >>
}
