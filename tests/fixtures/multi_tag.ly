\version "2.24.4"

% Tests that \tag with a multi-name list #'(foo bar) is removed
% when \removeWithTag #'foo is in effect (foo is in the tag set).

global = { \key c \major \time 4/4 }

melody = {
  \tag #'(foo bar) { c'4 }
  \tag #'bar { d'4 }
  \tag #'other { e'4 }
  f'4
}

\score {
  \removeWithTag #'foo
  \new Staff <<
    \global
    \melody
  >>
}
