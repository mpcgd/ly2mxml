\\version "2.24.4"

global = { \key c \major \time 4/4 }
melody = { a'16-.\sfp bes'16-. b'16-. c''8. }

\score {
  \new Staff <<
    \global
    \melody
  >>
}