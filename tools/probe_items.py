"""Probe python-ly item types for mark, breathe, key/time signature commands."""

import ly.document
import ly.music
from ly.music import items

src = r"""\score {
  \new Staff {
    c1
    \mark \default
    d1
    \mark #3
    e1
    \breathe
    f1
    \key g \major
    g1
    \time 3/4
    a4 b4 c4
    \tempo "Allegro"
    d4
    \tempo 4 = 120
    e4
  }
}
"""

doc = ly.document.Document(src)
tree = ly.music.document(doc)

def show(node, indent=0):
    token = str(getattr(node, "token", ""))
    print(" " * indent + type(node).__name__ + " token=" + repr(token))
    for child in node:
        show(child, indent + 2)

show(tree)
