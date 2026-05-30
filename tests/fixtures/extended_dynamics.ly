\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = {
  c'4\ppp c'4\pppp c'4\ffff c'4\fp
  c'4\fz c'4\rfz c'4\rf c'4\sfz
  c'4\sff c'4\sffz c'4\sfpp r4
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
