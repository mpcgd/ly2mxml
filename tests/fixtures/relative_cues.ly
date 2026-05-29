\version "2.24.4"

global = {
  \key c \major
  \time 4/4
}

quoteMusic = \relative c'' {
  c4 d e f
}

melody = \relative c' {
  \cueDuring #"quoteMusic" #UP { \relative c'4 { s1 } }
  c1
}

\addQuote "quoteMusic" \quoteMusic

\score {
  \new Staff <<
    \global
    \melody
  >>
}
