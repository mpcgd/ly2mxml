\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

melodyMusic = {
  c4 d e f
}

verseOneWords = \lyricmode {
  Hel -- lo world song
}

verseTwoWords = \lyricmode {
  Bye night moon light
}

lyricsOne = \lyricsto "melodyVoice" {
  \verseOneWords
}

lyricsTwo = \lyricsto "melodyVoice" {
  \verseTwoWords
}

\score {
  \new Staff <<
    \global
    \new Voice = "melodyVoice" \melodyMusic
    \new Lyrics \lyricsOne
    \new Lyrics \lyricsTwo
  >>
}