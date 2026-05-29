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
    """Thin wrapper around python-ly for project inspection and preflight analysis."""

    def __init__(self, loader: ProjectLoader | None = None) -> None:
        self.loader = loader or ProjectLoader()

    def load_document_tree(self, entrypoint: str | Path) -> items.Document:
        resolved_entrypoint = self.loader.resolve_entrypoint(entrypoint)
        return self._load_document(resolved_entrypoint)

    def inspect(self, entrypoint: str | Path) -> SourceAnalysis:
        resolved_entrypoint = self.loader.resolve_entrypoint(entrypoint)
        document = self._load_document(resolved_entrypoint)

        analysis = SourceAnalysis(entrypoint=resolved_entrypoint)
        self._visit_document(document, analysis, visited_paths=set())

        return analysis

    def _load_document(self, source_path: Path) -> items.Document:
        source_document = ly.document.Document.load(str(source_path))
        source_document.filename = str(source_path)
        return ly.music.document(source_document)

    def _visit_document(
        self,
        document: items.Document,
        analysis: SourceAnalysis,
        visited_paths: set[Path],
    ) -> None:
        file_name = getattr(document.document, "filename", None)
        resolved_file_name = Path(file_name).resolve() if file_name else None
        if resolved_file_name in visited_paths:
            return
        if resolved_file_name is not None:
            visited_paths.add(resolved_file_name)

        analysis.document_count += 1

        for node in self._walk_nodes(document):
            self._record_node(node, analysis)
            if isinstance(node, items.Include):
                included_document = document.get_included_document_node(node)
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
        yield node
        if isinstance(node, items.Item):
            for child in node:
                yield from self._walk_nodes(child)
