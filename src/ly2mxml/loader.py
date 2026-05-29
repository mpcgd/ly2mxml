"""Resolve LilyPond project files and cache their source text.

The loader is intentionally small, but it sits underneath both inspection and
conversion. Centralizing path resolution here keeps include handling,
entrypoint normalization, and repeated file reads consistent across the rest
of the pipeline.
"""

from __future__ import annotations

from pathlib import Path


class ProjectLoader:
    """Resolve and cache LilyPond source files for project inspection."""

    def __init__(self) -> None:
        self._text_cache: dict[Path, str] = {}

    def resolve_entrypoint(self, entrypoint: str | Path) -> Path:
        """Normalize a user-supplied LilyPond path into a concrete file path."""

        path = Path(entrypoint).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        resolved = path.resolve()

        if not resolved.exists():
            raise FileNotFoundError(f"LilyPond entrypoint does not exist: {resolved}")
        if resolved.is_dir():
            raise IsADirectoryError(f"Expected a LilyPond file, got directory: {resolved}")

        return resolved

    def read_text(self, source_path: str | Path) -> str:
        """Read and cache UTF-8 source text for a LilyPond file."""

        resolved = self.resolve_entrypoint(source_path)
        if resolved not in self._text_cache:
            self._text_cache[resolved] = resolved.read_text(encoding="utf-8")
        return self._text_cache[resolved]
