\version "2.24.4"

global = {
  \key c \major
  	ime 4/4
}

melody = \relative c' {
  R1*4
  c1
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}