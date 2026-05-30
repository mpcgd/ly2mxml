\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = { c'4\upbow d'4\downbow e'4\stopped f'4\open }

\score {
  \new Staff <<
    \global
    \melody
  >>
}
