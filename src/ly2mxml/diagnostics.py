from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class SourceLocation:
    file_path: Path | None
    position: int | None = None
    end_position: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": str(self.file_path) if self.file_path else None,
            "position": self.position,
            "end_position": self.end_position,
        }


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: Severity
    location: SourceLocation = field(default_factory=lambda: SourceLocation(file_path=None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "location": self.location.to_dict(),
        }


def location_from_item(item: object) -> SourceLocation:
    document = getattr(item, "document", None)
    raw_file_path = getattr(document, "filename", None)
    file_path = Path(raw_file_path).resolve() if raw_file_path else None
    position = getattr(item, "position", None)
    end_position = None
    end_position_method = getattr(item, "end_position", None)
    if callable(end_position_method):
        end_position = end_position_method()
    return SourceLocation(file_path=file_path, position=position, end_position=end_position)
