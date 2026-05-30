\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = {
  c'1 \bar "|:"
  d'1 \bar ":|"
  e'1 \bar "||"
  f'1 \bar ".|."
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
