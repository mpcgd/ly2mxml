\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = {
  \stemUp c'4 d'4
  \stemDown e'4 f'4
  \stemNeutral g'4 a'4 b'4 c''4
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
