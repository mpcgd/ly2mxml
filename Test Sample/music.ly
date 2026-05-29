% Music definitions shared between score and parts
% Include this file in both score and part files
\version "2.24.4"

\include "config.ly"

% Global settings
global = {
  \key f \major 
  \time 6/8
  \tempo "Maestoso"
}

% Global settings for instruments without key signature (Horn, Trumpet)
globalNoKey = {
  \key c \major
  \time 6/8
  \tempo "Maestoso"
}

% Music variables for each instrument
fluteI = \relative c'' { \compressEmptyMeasures 
a'2.\<
a4\trill r8 a4\trill\! r8
a8\trill r8 c16. c32 f8 r c16. c32
f4 r8 r4 r8
c2.
d16( c) d( c) d( c) d( c) d( c) d( c)
c4 r8 r4 r8
R2.*3
c2.\<
c4\trill\! r8 c4\trill r8
c8 r c16. c32 e8 r c16. c32
e4 r8 r4 r8
e2.\trill
f16( e) f( e) f( e) f( e) f( e) f( e)
\appoggiatura {g,8} e'4 r8 r4 r8
\appoggiatura {g,8} e'4 r8 \appoggiatura {g,8} e'4 r8
\appoggiatura {g,8} e'4\trill r8 r4 r8
R2.
a,8\p r8 c16. c32 a8 r8 c16. c32
a8 r8 c16. c32 a8 r8 c16. c32
a8-.\cresc c16( a) c( a) c( a) c( a) c( a)
bes(\f a g fis g a) bes8-. c-. d-.
c a f g-. c,( c')
a f' f f f f
f4 r8 f4 r8
f4 r8 r4 r8
R2.*3
r4 r8 c8( b) d-.
c4 a8 bes4 d8
g,4. b8-. d-. b8-. 
c4 e8 d4 f8
e4 r8 b8 d b8
c4 e8 d f d
c4. b 
c8 c16( g) e-. g-. c8 c16( g) e-. g-.
c8 c c c c c
c4 r8 c8-.\f d-. e-.
f4-. f8-. es( f) es
d4 r8 a8( d->) c-.
bes( a g) a( d->) c-.
bes( a) g b-. c-. d-.
c4 c8 \acciaccatura {e8} d8 c d
e4. c8-.\f e-. g-.
f e d c bes a
d c bes a g f
c' c c c c c
\bar "||"
c8\f g16( f e d) c8 r r
R2.*4
c'2.\trill~
c\trill~
c\trill
a8 f' f f4 r8
R2.
d8 d d d4 r8
R2.
e8 e e e4 r8
e2.
f4. d
c
e,
f4 r8 r4 r8
R2.
d'8 d d d4 r8
R2.
e8 e e e4 r8
e2.
f4. d
c e
f8 f f f f f
f4 r8
\bar "|."
 }
fluteII = \relative c'' { \compressEmptyMeasures 
f2.\<
f4\trill r8 f4\trill\! r8
f8\trill r8 a16. a32 a8 r a16. a32
a4 r8 r4 r8
a2.
bes16( a) bes( a) bes( a) bes( a) bes( a) bes( a)
a4 r8 r4 r8
R2.*3
e2.\<
e4\trill\! r8 e4\trill r8
e8 r bes'16. bes32 g8 r bes16. bes32
g4 r8 r4 r8
g2.\trill
a16( g) a( g) a( g) a( g) a( g) a( g)
\appoggiatura {a8} g4 r8 r4 r8
\appoggiatura {a8} g4 r8 \appoggiatura {a8} g4 r8
\appoggiatura {a8} g4\trill r8 r4 r8
R2.
f,8\p r8 a'16. a32 f8 r8 a16. a32
f8 r8 a16. a32 f8 r8 a16. a32
f8-.\cresc a16( f) a( f) a( f) a( f) a( f)
f8\f f f f f f 
a f c bes g bes
a a' a a a a
a4 r8 a4 r8
a4 r8 r4 r8
R2.*4
a4 f8 f4 f8
e4. g4.\trill~
g2.
g4 r8 r4 r8
g4 g8 f a f
e4. d 
e4 r8 e4 r8
e8 e e e e e
e4 r8 r4 r8
r8 a\sf bes c4( bes8)
a4 r8 d,4.->~
d4. d4.->~
d4. g8 g g
g4 g8 g g g
g4. c\sf
c8 r r r4 r8
d c bes a g f
e e e e e e
\bar "||"
c'8\f g16( f e d) c8 r r
R2.*4
bes'2.
a
e
f8 a a a4 r8
R2.
bes8 bes bes bes4 r8
R2.
c8 c c c4 r8
a4. g
a bes
a g
f4 r8 r4 r8
R2.
bes8 bes bes bes4 r8
R2.
c8 c c c4 r8
a4. g
a4. bes
a g
f8 f f f f f
f4 r8
\bar "|." }

hautboisI = \relative c'' { \compressEmptyMeasures }
hautboisII = \relative c'' { \compressEmptyMeasures }

clarinetteI = \relative c'' { \compressEmptyMeasures 
f2.~\<
f2.
f8(-.\> f-. f-.) f(-. f-. f-.)\!
\appoggiatura g8 f4 r8 \appoggiatura g8 f4 r8
f8(\< c a') f( c a')
f8(\> c a') f( c a')
f4.\! c4( a'8)
f8. a16-.\sfp bes-. b-. c8. a16-.\sfp bes-. b-.
c4.( a
f a)
g2.\<~
g2.\>
g8(-. g-. g-.) g(-. g-. g-.)\!
\appoggiatura a8 g4 r8 \appoggiatura {a8} g4 r8
g8(\< c, bes') g( c, bes')
g(\> c, bes') g( c, bes')\!
g4.( c,4 bes'8)
g8. fis16-.\sfp g-. a-. bes8. fis16-.\sfp g-. a-.
bes4.( g c, bes')
a8\p r8 c16. c32 a8 r8 c16. c32
a8 r8 c16. c32 a8 r8 c16. c32
a8-.\cresc c16( a) c( a) c( a) c( a) c( a)
bes(\f a g fis g a) bes8-. c-. d-.
c a f g-. c,( c')
f, f f f f f
f4 r8 f4 r8
f4 r8 c8( b) d
c4\p a8 bes4 d8
g,4. f8\cresc a c
f4\! a,8 bes4 d8
c8( bes) a-. c( b) d-.
c4 a8 bes4 d8
g,4. b8-. d-. b8-. 
c4( e8) d8( g f8)
e16( g f e d c) b8-. d-. b8-.
c4( e8) d-. f-. d-.
 e8( c') c-. d,( b') b-. 
c8 c16( g) e-. g-. c8 c16( g) e-. g-.
c8 c c c c c
c4 r8 c,8-.\f d-. e-.
f4-. f8-. es( f) es
d4 r8 a8( d->) c-.
bes( a g) a( d->) c-.
bes( a) g b-. c-. d-.
c4 c8 \acciaccatura {e8} d8 c d
e4. c8-.\f e-. g-.
f e d c bes a
d c bes a g f
c' c' c c c c
\bar "||"
c8\f g16( f e d) c8 r r
c8(\f g' e) c8( g' e)
c8( a' f) c8( a' f)
c8( g' e) c8( g' e)
c8( a' f) c8( a' f)
c8( g' e) c8( g' e)
c8( a' f) c8( a' f)
c8( g' e) c8( g' e)
f f f f4 r8
f8(\ff g) f-. f( g) f-.
f4. \appoggiatura {d32 f} bes8 r r
g8( a) g-. g( a) g-.
g4. \appoggiatura{e32 g} c4-. g8
a4 a8 g4 g8
f4 f8 g a g
f8 f f e e e
f\f a, bes c d e
f8( g) f-. f8( g) f-.
f4. \appoggiatura {d32 f} bes8-. r r
g8( a) g-. g( a) g-.
g4. \appoggiatura{e32 g} c4-. g8
a4 a8 g8( a g)
f4 f8 g8( a) g-.
f8 f f e e e 
f f f f f f 
f4 r8
\bar "|."
}
clarinetteII = \relative c'' { \compressEmptyMeasures 
f,8(\< c a') f( c a')
f8( c a') f( c a')
f8(\> c a') f( c a')\!
f8( c a') f( c a')
a2.\<~
a2.\>
g8(\! c, bes') g( c, bes')
g8( c, bes') g( c, bes')
g8( c, bes') g( c, bes')
g8( c, bes') g( c, bes')
bes2.\<~
bes~\>
bes\!
bes4 r8 bes4 r8
e,8( g c,) e( g c,)
e8( g c,) e( g c,)
f8(-.\> f-. f-.) f(-. f-. f-.)
\appoggiatura g8 f4\! r8 \appoggiatura g8 f4 r8
f8(\< c a') f( c a')
f8(\> c a') f( c a')
f8\p r8 a'16. a32 f8 r8 a16. a32
f8 r8 a16. a32 f8 r8 a16. a32
f8-.\cresc a16( f) a( f) a( f) a( f) a( f)
f8\f f f f f f 
a f c bes g bes
a a a a a a
a4 r8 a4 r8
a4 r8 r4 r8
a4\p f8 f4 f8
e c e f\cresc a c\!
a4 f8 g4 bes8
a8( g) f-. r4 r8
a4 f8 f4 f8
e4. g8 g g
g g g g g g
g g g g g g
g g g a a a
g( e') e-. g,( f') f-.
e4\f r8 e4 r8
e8 e e e e e
e 4 r8 r4 r8
r8 a,\sf bes c4( bes8)
a4 r8 d,4.->~
d4. d4.->~
d4. g8 g g
g4 g8 g g g
g4. c\sf
c8 r r r4 r8
d c bes a g f
e e' e e e e
\bar "||"
c8\f g'16( f e d) c8 r r
c8\f c c c c c
c c c c c c
c c c c c c
c c c c c c
c c c c c c
c c c c c c
c c c c c c
c a a a4 r8
c\ff c c c c c
d d d d4 r8
d d d d d d 
e e e e4 r8
d4 d8 d4 d8
a4.( d)
a8 a a bes bes bes
a\f f g a bes g
c c c c c c
d d d d4 r8
d d d d d d 
e e e e4 r8
d4 d8 d4 d8
a4.( d)
a8 a a bes bes bes
a8 a a a a a
a4 r8
}

bassonI = \relative c { \clef bass \compressEmptyMeasures 
f2.~\<
f~
f\>
f4\! r8 f4 r8
f2.~
f~
f
f4 r8 f4 r8
f2.~
f2.
bes2.~\<
bes~\>
bes
c4\! r8 c4 r8
c2.~\<
c~\>
c~\!
c4 r8 c4 r8
c,2.~
c
f8\sf f, r f'\sf f, r
f'8\sf f, r f'\sf f, r
f8\f f' f f\cresc f f
d'16(\f c bes a bes c) d8 c b
c c c c, c c
f f c a c a
f4 r8 f4 r8
f4 r8 r4 r8
f'4\p r8 d4 bes8
c e c a'\cresc bes c\!
f,4 es8 d4 bes8
c8 e f r4 r8
f4 r8 d4 bes8
c e g f4.->
e8 d c b4.->
c8-. d-. e-. f4.->
e8 d c f f f
g g g g, g g
c4\f r8 c4 r8
c8 c' g e g e
c4 r8 r4 r8
r8 f8\ff g a4( g8)
fis4 r8 fis4\sf d8
g( a bes) fis4 d8
g8 a bes f!4.\sf
e8 d c b a g
c e g bes!4.\sf
f8 r8 r8 r4 r8
d'8 c bes a g f
c e g c g e
\bar "||"
c8\f g'16( f e d) c8 r r
e4\f r8 e4 r8
f4 r8 f4 r8
bes4 r8 bes4 r8
a4 r8 a4 r8
e4 r8 e4 r8
f4 r8 f4 r8
bes4 r8 bes4 r8
a8 f f f4 r8
a8\ff a a a a a
bes f d bes4 r8
b'!8 b b b b b
c g e c4 r8
cis'8 cis cis a a a
d d d bes bes bes
c c c c, c c
f4 r8 r4 r8
a8 a a a a a 
bes f d bes4 r8
b'8 b b b b b
c g e c4 r8
cis'8 cis cis a a a 
d d d bes bes bes
c c c c, c c
f f f f f f 
f4 r8


}
bassonII = \relative c { \clef bass \compressEmptyMeasures
f,2.~\<
f~
f\>
f4\! r8 f4 r8
f2.~
f~
f
f4 r8 f4 r8
f2.~
f2.
c'2.~\<
c~\>
c
c4\! r8 c4 r8
c2.~\<
c~\>
c~\!
c4 r8 c4 r8
c2.~
c
f8\sf f, r f'\sf f, r
f'8\sf f, r f'\sf f, r
f8\f f' f f\cresc f f
d'16(\f c bes a bes c) d8 c b
c c c c, c c
f f c a c a
f4 r8 f4 r8
f4 r8 r4 r8
f'4\p r8 d4 bes8
c e c a\cresc bes c\!
f4 es8 d4 bes8
c8 e f r4 r8
f4 r8 d4 bes8
c e g f4.->
e8 d c b4.->
c8-. d-. e-. f4.->
e8 d c f f f
g g g g, g g
c4\f r8 c4 r8
c8 c' g e g e
c4 r8 r4 r8
r8 f8\ff g a4( g8)
fis4 r8 fis4\sf d8
g( a bes) fis4 d8
g8 a bes f!4.\sf
e8 d c b a g
c e g bes!4.\sf
f8 r8 r8 r4 r8
d'8 c bes a g f
c e g c g e
\bar "||"
c8\f g'16( f e d) c8 r r
e4\f r8 e4 r8
f4 r8 f4 r8
bes4 r8 bes4 r8
a4 r8 a4 r8
e4 r8 e4 r8
f4 r8 f4 r8
bes4 r8 bes4 r8
a8 f f f4 r8
a8\ff a a a a a
bes f d bes4 r8
b'!8 b b b b b
c g e c4 r8
cis'8 cis cis a a a
d d d bes bes bes
c c c c, c c
f4 r8 r4 r8
a8 a a a a a 
bes f d bes4 r8
b'8 b b b b b
c g e c4 r8
cis'8 cis cis a a a 
d d d bes bes bes
c c c c, c c
f f f f f f 
f4 r8
}

corI = \relative c'' { \compressEmptyMeasures
c2.\<~
c2.
c4\! r8 r4 r8
r4 g'8 e4 g8
e4 r8 r4 r8
R2.
c2.
c4 r8 c4 r8
c4 r8 r4 r8
R2.
d2.\<~ 
d2.\>
d4\! r8 r4 r8
r4 f8 d4 f8
d4 r8 r4 r8
R2.
r4 f8 d4 f8
d4 r8 d4 r8
d4 r8 r4 r8
R2.
c4 r8 c4 r8
c4 r8 c4 r8
c8 c c c\< c c
c4\f r8 r4 r8
e8 e e d d d
c c c c c c
c4 r8 c4 r8
c4 r8 r4 r8
c2.\p(
d4) r8 r4 r8
c4 c8 c4 c8
e8 d c r4 r8
c2.
c8 c c d4.~
d2.
d4. d8\cresc d d
d4. e4 e8
d2.
d4\f r8 d4 r8
d8 d d d d d
d4 r8 r4 r8
R2.
r4 r8 r4 e8(->
f4) r8 r4 e8->(
d4) r8 d8 d d
d4 d8 d d d
d4 r8 r4 r8
R2.*2
d8 d d d d d
\bar "||"
d4 r8 r4 r8
\appoggiatura a'8 g4\f r8 \appoggiatura a8 g4 r8
\appoggiatura a8 g4 r8 \appoggiatura a8 g4 r8
\appoggiatura a8 g4 r8 \appoggiatura a8 g4 r8
\appoggiatura a8 g4 r8 \appoggiatura a8 g4 r8
\appoggiatura a8 g4 r8 \appoggiatura a8 g4 r8
\appoggiatura a8 g4 r8 \appoggiatura a8 g4 r8
\appoggiatura a8 g4 r8 \appoggiatura a8 g4 r8
e8 e e e4 r8
c4.\ff c
c8 c c c4 r8
d4. d
d8 d d d4 r8
e4. e
e4 e8 d8 e d
e4 r8 d4 r8
c4 r8 r4 r8
c2. 
c8 c c c4 r8
d2.
d8 d d d4 r8
e4 r8 e4 r8
e4 e8 d8 e d
e4 r8 d4 r8
c8 c c c c c
c4 r8

}
corII = \relative c'' { \compressEmptyMeasures 
e,2.\<~
e2.
e4\! r8 r4 r8
r4 e'8 c4 e8
c4 r8 r4 r8
R2.
e,2.
e4 r8 e4 r8
e4 r8 r4 r8
R2.
g2.\<~ 
g2.\>
g4\! r8 r4 r8
r4 d'8 g,4 d'8
g,4 r8 r4 r8
R2.
r4 d'8 g,4 d'8
g,4 r8 g4 r8
g4 r8 r4 r8
R2.
e4 r8 e4 r8
e4 r8 e4 r8
e8 e e e\< e e
c4\f r8 r4 r8
c'8 c c g g g
e e e e e e
e4 r8 e4 r8
e4 r8 r4 r8
c2.\p(
g'4) r8 r4 r8
c,4 c8 c4 c8
c'8 g e r4 r8
c2.
g'8 g g d'4.~
d2.
d4. d8\cresc d d
g,4. c4 c8
g4. d'
g,4\f r8 g4 r8
g8 g g g g g
g4 r8 r4 r8
R2.
r4 r8 r4 cis8(->
d4) r8 r4 cis8->(
d4) r8 d8 d d
d4 d8 d d d
g,4 r8 r4 r8
R2.*2
g8 g g g g g
\bar "||"
g4 r8 r4 r8
g2.~\f
g2.~
g2.~
g2.~
g2.~
g2.~
g2.
c8 c c c4 r8
c,4.\ff c
c8 c c c4 r8
d'4. d
g,8 g g g4 r8
d'4. d
c4 c8 d8 e d
c4 r8 g4 r8
e4 r8 r4 r8
c2. 
c8 c c c4 r8
d'2.
g,8 g g g4 r8
c4 r8 d4 r8
c4 c8 d8 e d
c4 r8 g4 r8
e8 e e e e e
e4 r8
}

trompetteI = \relative c'' { \compressEmptyMeasures 
g2.~\<
g
g4\! r8 r4 r8
R2.*7
g2.~\<
g\>
g4\! r8 r4 r8
R2.*9
c8 c c c c c
c4 r8 r4 r8
c c c g g g
g g g g g g
g4 r8 g4 r8
g4 r8 r4 r8
R2.*10
g4\f r8 g4 r8
g8 g g g g g
g4 r8 r4 r8
R2.*8
g8 g g g g g
\bar "||"
g4\f r8 r4 r8
g2.\f~
g2.~
g2.~
g2.~
g2.~
g2.~
g2.
g8 g g g4 r8
R2.
c,8 c c c4 r8
R2.
g'8 g g g4 r8
R2.*2
g4 r8 g4 r8
g4 r8 r4 r8
R2.
c,8 c c c4 r8
R2.
g'8 g g g4 r8
R2.*3
e8 e e e e e
e4 r8
}
trompetteII = \relative c'' { \compressEmptyMeasures 
e,2.~\<
e
e4\! r8 r4 r8
R2.*7
g,2.~\<
g\>
g4\! r8 r4 r8
R2.*9
c8 c c c c c
c4 r8 r4 r8
e e e g g g 
e e e e e e
e4 r8 e4 r8
e4 r8 r4 r8
R2.*10
g,4\f r8 g4 r8
g8 g g g g g
g4 r8 r4 r8
R2.*8
g8 g g g g g
\bar "||"
g4\f r8 r4 r8
g2.\f~
g2.~
g2.~
g2.~
g2.~
g2.~
g2.
e'8 e e e4 r8
R2.
c8 c c c4 r8
R2.
g8 g g g4 r8
R2.*2
g4 r8 g4 r8
g4 r8 r4 r8
R2.
c8 c c c4 r8
R2.
g'8 g g g4 r8
R2.*3
c,8 c c c c c 
c4 r8
}

tromboneI = \relative c { \clef bass \compressEmptyMeasures 
a'2.~\<
a
a4\! r8 r4 r8
R2.*7
g2.~\<
g\>
g4\! r8 r4 r8
R2.*9
a8 a a a a a
f4 r8 r4 r8
c' c c c, c c
f f c a c a
f4 r8 f4 r8
f4 r8 r4 r8R2.*10
g'4\f r8 g4 r8
g8 g g g g g
g4 r8 r4 r8
R2.*8
g4 r8 g4 r8
\bar "||"
g4\f r8 r4 r8
R2.*9
f8 f f f4 r8
R2.
c'8 g e c4 r8
cis'8 cis cis a a a
d d d bes bes bes
c c c c, c c
f4 r8 r4 r8
a8 a a a a a 
bes f d bes4 r8
b'8 b b b b b
c g e c4 r8
cis'8 cis cis a a a 
d d d bes bes bes
c c c c, c c
f f f f f f 
f4 r8

}
tromboneII = \relative c { \clef bass \compressEmptyMeasures
c2.~\<
c
c4\! r8 r4 r8
R2.*7
e2.~\<
e\>
e4\! r8 r4 r8
R2.*9
f8 f f f f f
f4 r8 r4 r8
c' c c c, c c
f f c a c a
f4 r8 f4 r8
f4 r8 r4 r8R2.*10
e'4\f r8 e4 r8
e e e e e e
e4 r8 r4 r8
R2.*8
e4 r8 e4 r8
\bar "||"
e4\f r8 r4 r8
R2.*9
d8 d d d4 r8
R2.
c'8 g e c4 r8
cis'8 cis cis a a a
d d d bes bes bes
c c c c, c c
f4 r8 r4 r8
a8 a a a a a 
bes f d bes4 r8
b'8 b b b b b
c g e c4 r8
cis'8 cis cis a a a 
d d d bes bes bes
c c c c, c c
f f f f f f 
f4 r8
}
tromboneIII = \relative c { \clef bass \compressEmptyMeasures 
f,2.~\<
f
f4\! r8 r4 r8
R2.*7
c'2.~\<
c\>
c4\! r8 r4 r8
R2.*11
c'8 c c c, c c
f f c a c a
f4 r8 f4 r8
f4 r8 r4 r8R2.*10
c'4\f r8 c4 r8
c c c c c c 
c4 r8 r4 r8
R2.*8
c4 r8 c4 r8
\bar "||"
c4\f r8 r4 r8
R2.*9
bes8 bes bes bes4 r8
R2.
c'8 g e c4 r8
cis'8 cis cis a a a
d d d bes bes bes
c c c c, c c
f4 r8 r4 r8
a8 a a a a a 
bes f d bes4 r8
b'8 b b b b b
c g e c4 r8
cis'8 cis cis a a a 
d d d bes bes bes
c c c c, c c
f f f f f f 
f4 r8
}

serpent = \relative c { \clef bass \compressEmptyMeasures R1*10 }

violonI = \relative c'' { \compressEmptyMeasures R2.*27
r4 r8 c8( b) d
c4\p a8 bes4 d8
g,4. f8\cresc a c
f4\! a,8 bes4 d8
c8( bes) a-. c( b) d-.
c4 a8 bes4 d8
g,4. b8-. d-. b8-. 
c4( e8) d8( g f8)
e8( d c) b8-. d-. b8-.
c4( e8) d( f) d-.
c4. \appoggiatura e8 d4.
c4 r8 r4 r8
R2.
r4 r8 c8-.\f d-. e-.
f4-. f8-. es( f) es
d4 r8 a8( d->) c-.
bes( a g) a( d->) c-.
bes( a) g b-. c-. d-.
c4 c8 \acciaccatura {e8} d8( c) d
e4 r8 r4 c8
f e d c( bes) a
d c bes a g f
c'2.
\bar "||"
}
violonII = \relative c'' { \compressEmptyMeasures R2.*50 }
alto = \relative c' { \clef alto \compressEmptyMeasures R2.*50 }
violoncelle = \relative c { \clef bass \compressEmptyMeasures R2.*50 }
contrebasse = \relative c { \clef bass \compressEmptyMeasures R1*10 }

% Include cues at the end of music definitions so they have access to all variables
\include "cues.ly"
