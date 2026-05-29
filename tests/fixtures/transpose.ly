\version "2.24.4"

global = \transpose c d {
  \key c \major
  \time 4/4
}

melody = \transpose c d {
  c4 d e f
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}