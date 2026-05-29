\version "2.24.4"

global = { \key f \major \time 6/8 }
melody = \relative c {
  f,2.~
  f~
  f
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}