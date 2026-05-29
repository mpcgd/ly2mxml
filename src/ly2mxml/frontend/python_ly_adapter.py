"""Bridge python-ly parsing to the rest of the project.

This module keeps parser-facing concerns isolated from conversion concerns. It
loads documents, follows includes, walks parser nodes, and records the feature
usage that preflight and the CLI expose to users.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import ly.document
import ly.music
from ly.music import items

from ly2mxml.diagnostics import Diagnostic, location_from_item
from ly2mxml.loader import ProjectLoader


@dataclass(slots=True)
class SourceAnalysis:
    """Summarize parser-facing facts discovered while inspecting a project."""

    entrypoint: Path
    document_count: int = 0
    scheme_node_count: int = 0
    included_files: set[Path] = field(default_factory=set)
    assignments: set[str] = field(default_factory=set)
    features: set[str] = field(default_factory=set)
    command_counts: Counter[str] = field(default_factory=Counter)
    user_command_counts: Counter[str] = field(default_factory=Counter)
    context_counts: Counter[str] = field(default_factory=Counter)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the analysis in a stable shape for CLI and tests."""

        return {
            "entrypoint": str(self.entrypoint),
            "document_count": self.document_count,
            "scheme_node_count": self.scheme_node_count,
            "included_files": [str(path) for path in sorted(self.included_files)],
            "assignment_count": len(self.assignments),
            "assignments": sorted(self.assignments),
            "features": sorted(self.features),
            "command_counts": dict(sorted(self.command_counts.items())),
            "user_command_counts": dict(sorted(self.user_command_counts.items())),
            "context_counts": dict(sorted(self.context_counts.items())),
            "diagnostic_count": len(self.diagnostics),
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


class PythonLyAdapter:
    """Wrap python-ly loading and inspection behind project-specific helpers.

    The adapter intentionally does not implement musical conversion. Its job is
    to provide a consistent document tree and inspection summary that the
    converter can trust.
    """

    def __init__(self, loader: ProjectLoader | None = None) -> None:
        self.loader = loader or ProjectLoader()

    def load_document_tree(self, entrypoint: str | Path) -> items.Document:
        """Load the parsed document tree for the conversion pipeline."""

        resolved_entrypoint = self.loader.resolve_entrypoint(entrypoint)
        return self._load_document(resolved_entrypoint)

    def inspect(self, entrypoint: str | Path) -> SourceAnalysis:
        """Inspect a LilyPond project, following includes transitively."""

        resolved_entrypoint = self.loader.resolve_entrypoint(entrypoint)
        document = self._load_document(resolved_entrypoint)

        analysis = SourceAnalysis(entrypoint=resolved_entrypoint)
        self._visit_document(document, analysis, visited_paths=set())

        return analysis

    def _load_document(self, source_path: Path) -> items.Document:
        """Parse one LilyPond file into the python-ly music tree."""

        source_text = self.loader.read_text(source_path)
        source_document = ly.document.Document(source_text, mode="lilypond")
        source_document.filename = str(source_path)
        return ly.music.document(source_document)

    def load_included_document(self, document: items.Document, include_node: items.Include) -> items.Document | None:
        """Resolve and parse a file referenced by one ``\\include`` node."""

        include_path = self._resolve_include_path(document, include_node)
        if include_path is None:
            return None
        try:
            return self._load_document(include_path)
        except (FileNotFoundError, IsADirectoryError):
            return None

    def _resolve_include_path(self, document: items.Document, include_node: items.Include) -> Path | None:
        """Resolve an include relative to the including document when needed."""

        include_name = include_node.filename()
        if not include_name:
            return None

        source_file_name = getattr(document.document, "filename", None)
        include_path = Path(include_name)
        if source_file_name and not include_path.is_absolute():
            include_path = Path(source_file_name).resolve().parent / include_path

        return self.loader.resolve_entrypoint(include_path)

    def _visit_document(
        self,
        document: items.Document,
        analysis: SourceAnalysis,
        visited_paths: set[Path],
    ) -> None:
        """Walk one document once and recurse through any resolvable includes."""

        file_name = getattr(document.document, "filename", None)
        resolved_file_name = Path(file_name).resolve() if file_name else None
        if resolved_file_name in visited_paths:
            return
        if resolved_file_name is not None:
            visited_paths.add(resolved_file_name)

        analysis.document_count += 1

        # Inspection follows includes here so the rest of the project can treat
        # the reported assignments, features, and diagnostics as whole-project
        # facts rather than facts from only the entrypoint file.
        for node in self._walk_nodes(document):
            self._record_node(node, analysis)
            if isinstance(node, items.Include):
                included_document = self.load_included_document(document, node)
                if included_document is None:
                    analysis.diagnostics.append(
                        Diagnostic(
                            code="unresolved-include",
                            message=f"Unable to resolve include: {node.filename()}",
                            severity="warning",
                            location=location_from_item(node),
                        )
                    )
                    continue

                included_file_name = getattr(included_document.document, "filename", None)
                if included_file_name:
                    analysis.included_files.add(Path(included_file_name).resolve())
                self._visit_document(included_document, analysis, visited_paths)

    def _record_node(self, node: object, analysis: SourceAnalysis) -> None:
        """Update the running analysis with information from one parser node."""

        if isinstance(node, items.Assignment):
            analysis.assignments.add(str(node.name()))

        if isinstance(node, items.Command):
            token = str(node.token)
            analysis.command_counts[token] += 1
            self._record_feature(token, analysis)

        if isinstance(node, items.UserCommand):
            name = node.name()
            analysis.user_command_counts[name] += 1
            self._record_feature(name, analysis, is_user_command=True)
            if node.value() is None:
                analysis.diagnostics.append(
                    Diagnostic(
                        code="unresolved-user-command",
                        message=f"Unresolved LilyPond command or variable: \\{name}",
                        severity="warning",
                        location=location_from_item(node),
                    )
                )

        if isinstance(node, items.Context):
            context_name = str(node.context())
            analysis.context_counts[context_name] += 1

        if isinstance(node, items.Scheme):
            analysis.scheme_node_count += 1
            analysis.features.add("scheme")

        if isinstance(node, items.Grace | items.AfterGrace):
            analysis.features.add("grace-notes")

        if isinstance(node, items.Scaler):
            analysis.features.add("scaled-durations")

        if isinstance(node, items.Repeat):
            specifier = node.specifier() or "unknown"
            analysis.features.add(f"repeat:{specifier}")

        if isinstance(node, items.Relative):
            analysis.features.add("relative-pitch")

        if isinstance(node, items.Transpose):
            analysis.features.add("transpose")

        if isinstance(node, items.LyricMode | items.LyricsTo):
            analysis.features.add("lyrics")

    def _record_feature(self, token: str, analysis: SourceAnalysis, is_user_command: bool = False) -> None:
        """Map low-level command tokens to the repository's support vocabulary."""

        normalized = token.lstrip("\\")
        interesting = {
            "bar": "barlines",
            "killCues": "cue-filtering",
            "addQuote": "cue-quotes",
            "partCombine": "part-combine",
            "removeWithTag": "tag-filtering",
            "compressEmptyMeasures": "multi-measure-rests",
            "unfoldRepeats": "repeat-expansion",
            "appoggiatura": "grace-notes",
            "acciaccatura": "grace-notes",
        }
        feature = interesting.get(normalized)
        if feature:
            analysis.features.add(feature)
        elif is_user_command and normalized and normalized[0].islower():
            analysis.features.add("user-variables")

    def _walk_nodes(self, node: object) -> Iterable[object]:
        """Yield one node and all of its parser children recursively."""

        yield node
        if isinstance(node, items.Item):
            for child in node:
                yield from self._walk_nodes(child)
