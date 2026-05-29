\version "2.24.4"

global = {
  \key c \major
  \time 6/8
}

melody = \relative c' {
  \compressEmptyMeasures
  R1*10
  c4. r4.
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}