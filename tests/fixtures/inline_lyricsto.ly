\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

melodyMusic = {
  c4 d e f
}

\score {
  \new Staff <<
    \global
    \new Voice = "melodyVoice" \melodyMusic
    \new Lyrics { \lyricsto "melodyVoice" { Hel -- lo world } }
  >>
}
