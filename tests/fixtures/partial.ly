\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = { \partial 4 c'4 | d'1 | e'1 }

\score {
  \new Staff <<
    \global
    \melody
  >>
}
