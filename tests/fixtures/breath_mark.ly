\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = {
  c'4 d'4 e'4 f'4\breathe
  g'2 a'2\breathe
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
