\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = {
  \segno c'4 d'4 e'4 f'4
  g'4 a'4 b'4 c''4
  \coda d''4 e''4 f''4 g''4
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
