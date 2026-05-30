\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = {
  c'4 d'4 e'4 f'4
  \time 3/4
  g'4 a'4 b'4
  \time 6/8
  c''8 d''8 e''8 f''8 g''8 a''8
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
