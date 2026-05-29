from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ly2mxml.converter import LilypondConverter
from ly2mxml.frontend.python_ly_adapter import PythonLyAdapter
from ly2mxml.options import ExportOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ly2mxml",
        description="Inspect and convert LilyPond source projects.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect a LilyPond entrypoint and summarize parser-facing constructs.",
    )
    inspect_parser.add_argument("source", type=Path, help="Path to the LilyPond entrypoint file.")
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the summary as JSON.",
    )

    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert a LilyPond entrypoint to MusicXML.",
    )
    convert_parser.add_argument("source", type=Path, help="Path to the LilyPond entrypoint file.")
    convert_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output MusicXML path. Defaults to <source>.musicxml.",
    )
    convert_parser.add_argument(
        "--partcombine-mode",
        choices=("separate", "combined"),
        default="separate",
        help="Export partCombine pairs as separate parts or merge them back into one MusicXML part with multiple voices.",
    )
    convert_parser.add_argument(
        "--include-cues",
        action="store_true",
        help="Enable cue-note export when supported. By default cue notes are ignored.",
    )

    return parser


def format_summary(data: dict[str, object]) -> str:
    diagnostics = data["diagnostics"]
    included_files = data["included_files"]
    features = data["features"]

    lines = [
        f"Entrypoint: {data['entrypoint']}",
        f"Documents: {data['document_count']}",
        f"Included files: {len(included_files)}",
        f"Assignments: {data['assignment_count']}",
        f"Scheme nodes: {data['scheme_node_count']}",
        f"Diagnostics: {data['diagnostic_count']}",
    ]

    if features:
        lines.append("Features:")
        lines.extend(f"  - {feature}" for feature in features)

    if included_files:
        lines.append("Resolved includes:")
        lines.extend(f"  - {path}" for path in included_files)

    if diagnostics:
        lines.append("Diagnostics:")
        for diagnostic in diagnostics:
            location = diagnostic["location"]
            path = location["file_path"] or "<unknown>"
            position = location["position"]
            suffix = "" if position is None else f":{position}"
            lines.append(
                f"  - {diagnostic['severity'].upper()} {diagnostic['code']} at {path}{suffix}: {diagnostic['message']}"
            )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        adapter = PythonLyAdapter()
        analysis = adapter.inspect(args.source)
        data = analysis.to_dict()
        if args.json:
            json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(format_summary(data))
            sys.stdout.write("\n")
        return 0

    if args.command == "convert":
        export_options = ExportOptions(
            partcombine_mode=args.partcombine_mode,
            cue_mode="include" if args.include_cues else "ignore",
        )
        converter = LilypondConverter(export_options=export_options)
        output_path = args.output or args.source.with_suffix(".musicxml")
        result = converter.convert_file(args.source, output_path)
        for diagnostic in result.preflight.diagnostics:
            location = diagnostic.location.file_path if diagnostic.location else None
            prefix = f"{location}: " if location else ""
            sys.stderr.write(f"{diagnostic.severity.upper()}: {prefix}{diagnostic.message}\n")
        if result.score is not None:
            for diagnostic in result.score.diagnostics:
                location = diagnostic.location.file_path if diagnostic.location else None
                prefix = f"{location}: " if location else ""
                sys.stderr.write(f"{diagnostic.severity.upper()}: {prefix}{diagnostic.message}\n")

        if result.preflight.has_errors or result.score is None:
            return 1
        if any(diagnostic.severity == "error" for diagnostic in result.score.diagnostics):
            return 1

        sys.stdout.write(f"Wrote MusicXML to {result.output_path}\n")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
