\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = { c'4\mordent d'4\prall e'4\turn f'4\reverseturn }

\score {
  \new Staff <<
    \global
    \melody
  >>
}
