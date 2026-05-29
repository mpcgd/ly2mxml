\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

quoteMusic = \relative c'' {
  c4-. d e f
  g4 a b c
}

melody = \relative c' {
  \cueDuring #"quoteMusic" #UP { s1 }
  \killCues
  \cueDuring #"quoteMusic" #UP { s1 }
  c1
}

\addQuote "quoteMusic" \quoteMusic

\score {
  \new Staff <<
    \global
    \melody
  >>
}