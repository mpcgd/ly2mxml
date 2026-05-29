\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

melody = \relative c' {
  c4 d e f
}

words = \lyricmode {
  Hel -- lo world song
}

\score {
  \new Staff <<
    \global
    \melody
    \addlyrics { \words }
  >>
}