\version "2.24.4"
global = { \key c \major \time 4/4 }
melody = << { c'4 d' e' f' } \\ { e'4 f' g' a' } >>
\score {
  \new Staff <<
    \global
    \melody
  >>
}
