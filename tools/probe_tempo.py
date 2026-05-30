"""Probe Tempo node API."""
import ly.document
import ly.music
from ly.music import items

src_ly = r"""\score {
  \new Staff {
    c1
    \tempo "Allegro"
    d4
    \tempo 4 = 120
    e4
  }
}
"""

doc = ly.document.Document(src_ly)
tree = ly.music.document(doc)

def iter_all(n):
    yield n
    for c in n:
        yield from iter_all(c)

for n in iter_all(tree):
    if isinstance(n, items.Tempo):
        print("text():", n.text())
        dur = getattr(n, "duration", None)
        print("duration attr:", dur)
        for c in n:
            token = str(getattr(c, "token", ""))
            value = getattr(c, "value", lambda: None)()
            print("  child:", type(c).__name__, repr(token), "value:", value)
