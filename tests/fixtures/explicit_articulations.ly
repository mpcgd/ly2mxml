\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = {
  c'4\staccato d'4\tenuto e'4\marcato f'4\accent
  g'4\espressivo a'4\portato b'4\staccatissimo c''4
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
