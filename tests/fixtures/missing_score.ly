\version "2.24.4"

% A valid LilyPond file that intentionally omits the \score block.
% Used to verify the converter emits a missing-score diagnostic.

global = { \key c \major \time 4/4 }
melody = \relative c' { c4 d e f }
