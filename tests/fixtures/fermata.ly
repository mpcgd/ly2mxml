\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = {
  c'1\fermata
  d'2\shortfermata e'2
  f'2\longfermata g'2
  a'1\verylongfermata
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
