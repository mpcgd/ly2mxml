\\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = { \ottava #1 c''4 d'' \ottava #0 e''4 f'' }

\score {
  \new Staff <<
    \global
    \melody
  >>
}