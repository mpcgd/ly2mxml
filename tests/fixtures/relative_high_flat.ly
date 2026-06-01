\version "2.24.4"

global = { \key f \major \time 6/8 }
melody = \relative c'' {
  a'2.
  bes2.
  b2.
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}