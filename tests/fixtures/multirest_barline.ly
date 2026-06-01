\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

melody = \relative c' {
  \compressEmptyMeasures
  R1
  R1 \bar "||"
  c1
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}