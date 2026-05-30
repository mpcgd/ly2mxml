\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = {
  c'4\prallmordent d'4\prallprall e'4\downmordent f'4\upmordent
  c'4\lheel d'4\rheel e'4\ltoe f'4\rtoe
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
