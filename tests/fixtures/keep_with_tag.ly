\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = {
  \keepWithTag #'solo {
    \tag #'solo { c'4 }
    \tag #'tutti { d'4 }
    e'4
    \tag #'solo { f'4 }
  }
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
