% Configuration file for LilyPond scores
% Edit these variables for each new piece

\version "2.24.4"

% Piece information
#(define-public piece-title "Hymne à l'agriculture")
#(define-public composer "Jean-Xavier Lefèvre")
#(define-public arranger "")
#(define-public opus "")

% Instrumentation (add instrument names as needed)
#(define-public instruments '(
  "Flûte I"
  "Flûte II"
  "Hautbois I (ad lib.)"
  "Hautbois II (ad lib.)"
  "Clarinette I"
  "Clarinette II"
  "Basson I"
  "Basson II"
  "Cor I en Fa"
  "Cor II en Fa"
  "Trompette I en Fa"
  "Trompette II en Fa"
  "Trompette I en Ut"
  "Trompette II en Ut"
  "Trombone I"
  "Trombone II"
  "Trombone III"
  "Serpent"
  "Violon I (ad lib.)"
  "Violon II (ad lib.)"
  "Alto (ad lib.)"
  "Violoncelle (ad lib.)"
  "Contrebasse (ad lib.)"
))

% Page settings
#(define-public score-paper-size "a4")
#(define-public part-paper-size "a4")
#(define-public part-staff-size 23) % Default staff size for parts

% MIDI settings
#(define-public midi-tempo 4/4) % Base tempo marking
