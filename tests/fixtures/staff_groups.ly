\version "2.24.4"

global = { \key c \major \time 4/4 }
melodyA = { c'1 d'1 }
melodyB = { e'1 f'1 }

\score {
  \new StaffGroup <<
    \new Staff << \global \melodyA >>
    \new Staff << \global \melodyB >>
  >>
}
