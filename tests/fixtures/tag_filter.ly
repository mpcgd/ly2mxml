\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

melody = {
  \tag #'part { c4 }
  \tag #'score { d4 }
  e2
  r4
}

\score {
  \removeWithTag #'part
  <<
    \new Staff <<
      \global
      \melody
    >>
  >>
}