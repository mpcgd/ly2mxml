\\version "2.24.4"

global = { \key c \major \time 6/8 }
melody = { f'2.-> g'2. }

\score {
  \new Staff <<
    \global
    \melody
  >>
}