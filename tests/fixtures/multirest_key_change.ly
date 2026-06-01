\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

melody = \relative c' {
  \compressEmptyMeasures
  R1
  \key g \major
  R1
  c1
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}