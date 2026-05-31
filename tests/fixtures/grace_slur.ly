\version "2.24.4"

global = { \key c \major \time 4/4 }

melody = {
  \acciaccatura { e'8( } d'4)
  \appoggiatura { f'8~ } f'4
}

\score {
  \new Staff <<
    \global
    \melody
  >>
}
