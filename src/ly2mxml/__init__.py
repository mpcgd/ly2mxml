"""Expose package metadata for the LilyPond-to-MusicXML toolchain.

The main public behavior lives in the CLI entry points and in the
``LilypondConverter`` orchestration class. This module intentionally stays
small so package metadata can be imported without pulling in the full
conversion pipeline.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
