\version "2.24.4"

global = { \key c \major \time 6/8 }
melody = \relative c'' {
  c2.\trill~
  c~
  c
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}