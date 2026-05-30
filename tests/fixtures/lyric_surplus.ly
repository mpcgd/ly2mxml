\version "2.24.4"

% Lyrics deliberately have more syllables than the melody has notes.
% Used to verify the converter emits a lyric-surplus warning.

global = { \key c \major \time 4/4 }

melody = \relative c' { c4 d e f }

words = \lyricmode {
  one two three four five six
}

\score {
  \new Staff <<
    \global
    \melody
    \addlyrics { \words }
  >>
}
