"""Run repository validation with deterministic per-step logs.

The script mirrors the documented validation workflow while capturing each step
into stable log files under ``.validation/latest`` so longer pytest runs are not
ambiguous when terminal output is abbreviated.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".validation" / "latest"
IMPORTER_TESTS = [
    "tests/test_convert.py::test_music21_import_preserves_sample_text_and_tempo_signatures",
    "tests/test_convert.py::test_music21_import_preserves_sample_wedge_types",
    "tests/test_convert.py::test_music21_import_preserves_sample_trill_extensions",
]
STEP_DESCRIPTIONS = {
    "import-check": "Import the package through the current interpreter.",
    "cli-help": "Exercise the root CLI help and both subcommand help pages.",
    "support-tests": "Run loader, adapter, CLI, and writer pytest coverage.",
    "convert-tests": "Run the main conversion regression suite.",
    "full-tests": "Run the full pytest suite in one command.",
    "sample-convert": "Convert the acceptance sample to a fresh MusicXML file.",
    "music21-import": "Run the importer-backed sample checks when music21 is available.",
}
DEFAULT_STEPS = [
    "import-check",
    "cli-help",
    "support-tests",
    "convert-tests",
    "sample-convert",
    "music21-import",
]


@dataclass
class StepResult:
    name: str
    description: str
    status: str
    exit_code: int | None
    duration_seconds: float
    log_path: str
    commands: list[str]
    note: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run repository validation and capture each step to deterministic "
            "log files under .validation/latest."
        )
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where logs, summaries, and sample outputs will be written.",
    )
    parser.add_argument(
        "--step",
        dest="steps",
        action="append",
        choices=list(STEP_DESCRIPTIONS),
        help="Run only the named validation step. Repeat to select multiple steps.",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue running later steps after a failure instead of stopping early.",
    )
    parser.add_argument(
        "--skip-music21",
        action="store_true",
        help="Skip the importer-backed music21 step even if music21 is installed.",
    )
    return parser


def resolve_output_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def validation_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    src = str(SRC_ROOT)
    env["PYTHONPATH"] = src if not existing else os.pathsep.join([src, existing])
    return env


def format_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def step_commands(output_dir: Path) -> dict[str, list[list[str]]]:
    return {
        "import-check": [
            [sys.executable, "-c", "import ly2mxml; print(ly2mxml.__version__)"]
        ],
        "cli-help": [
            [sys.executable, "-m", "ly2mxml", "--help"],
            [sys.executable, "-m", "ly2mxml", "inspect", "--help"],
            [sys.executable, "-m", "ly2mxml", "convert", "--help"],
        ],
        "support-tests": [
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_loader.py",
                "tests/test_adapter.py",
                "tests/test_cli.py",
                "tests/test_writer.py",
                "-q",
                "-rA",
            ]
        ],
        "convert-tests": [
            [sys.executable, "-m", "pytest", "tests/test_convert.py", "-q", "-rA"]
        ],
        "full-tests": [
            [sys.executable, "-m", "pytest", "tests", "-q", "-rA"]
        ],
        "sample-convert": [
            [
                sys.executable,
                "-m",
                "ly2mxml",
                "convert",
                "Test Sample/score.ly",
                "-o",
                str(output_dir / "sample.musicxml"),
            ]
        ],
        "music21-import": [
            [sys.executable, "-m", "pytest", *IMPORTER_TESTS, "-q", "-rA"]
        ],
    }


def clear_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if not child.is_file():
            continue
        try:
            child.unlink()
        except OSError:
            continue


def write_summary(output_dir: Path, requested_steps: list[str], results: list[StepResult]) -> Path:
    completed_steps = [result.name for result in results]
    overall_status = "failed" if any(result.status == "failed" for result in results) else "passed"
    if len(completed_steps) < len(requested_steps) and overall_status == "passed":
        overall_status = "incomplete"
    if results and all(result.status == "skipped" for result in results):
        overall_status = "skipped"

    summary_data = {
        "repo_root": str(REPO_ROOT),
        "python_executable": sys.executable,
        "output_dir": str(output_dir),
        "requested_steps": requested_steps,
        "completed_steps": completed_steps,
        "missing_steps": [step for step in requested_steps if step not in completed_steps],
        "overall_status": overall_status,
        "results": [asdict(result) for result in results],
    }

    summary_json_path = output_dir / "summary.json"
    summary_json_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    lines = [
        f"overall_status: {overall_status}",
        f"python_executable: {sys.executable}",
        f"output_dir: {output_dir}",
        f"completed_steps: {', '.join(completed_steps) if completed_steps else '(none)'}",
        f"missing_steps: {', '.join(summary_data['missing_steps']) if summary_data['missing_steps'] else '(none)'}",
        "",
    ]
    for result in results:
        lines.append(
            " | ".join(
                [
                    result.name,
                    result.status,
                    f"exit_code={result.exit_code}",
                    f"duration={result.duration_seconds:.2f}s",
                    f"log={result.log_path}",
                ]
            )
        )
        if result.note:
            lines.append(f"note={result.note}")
    lines.append("")
    (output_dir / "summary.txt").write_text("\n".join(lines), encoding="utf-8")

    return summary_json_path


def skipped_step_result(index: int, name: str, output_dir: Path, note: str) -> StepResult:
    log_path = output_dir / f"{index:02d}-{name}.log"
    log_path.write_text(note + "\n", encoding="utf-8")
    return StepResult(
        name=name,
        description=STEP_DESCRIPTIONS[name],
        status="skipped",
        exit_code=None,
        duration_seconds=0.0,
        log_path=str(log_path),
        commands=[],
        note=note,
    )


def run_step(index: int, total_steps: int, name: str, output_dir: Path) -> StepResult:
    log_path = output_dir / f"{index:02d}-{name}.log"
    commands = step_commands(output_dir)[name]
    command_strings = [format_command(command) for command in commands]
    start_time = time.perf_counter()

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"step={name}\n")
        log_file.write(f"description={STEP_DESCRIPTIONS[name]}\n")
        log_file.write(f"cwd={REPO_ROOT}\n")
        log_file.write(f"python={sys.executable}\n\n")
        log_file.flush()

        exit_code = 0
        for command_index, command in enumerate(commands, start=1):
            log_file.write(f"=== command {command_index}/{len(commands)} ===\n")
            log_file.write(f"$ {format_command(command)}\n\n")
            log_file.flush()
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=validation_env(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            exit_code = result.returncode
            log_file.write(f"\n[exit code: {exit_code}]\n\n")
            log_file.flush()
            if exit_code != 0:
                break

    duration_seconds = time.perf_counter() - start_time
    status = "passed" if exit_code == 0 else "failed"
    print(f"[{index}/{total_steps}] {name}: {status.upper()} ({log_path})")

    return StepResult(
        name=name,
        description=STEP_DESCRIPTIONS[name],
        status=status,
        exit_code=exit_code,
        duration_seconds=duration_seconds,
        log_path=str(log_path),
        commands=command_strings,
    )


def main() -> int:
    args = build_parser().parse_args()
    requested_steps = args.steps or list(DEFAULT_STEPS)
    output_dir = resolve_output_dir(args.output_dir)
    clear_output_dir(output_dir)

    print(f"Writing validation logs to {output_dir}")

    results: list[StepResult] = []

    for index, step_name in enumerate(requested_steps, start=1):
        if step_name == "music21-import":
            if args.skip_music21:
                result = skipped_step_result(index, step_name, output_dir, "music21 importer step was skipped by request.")
                print(f"[{index}/{len(requested_steps)}] {step_name}: SKIPPED ({result.log_path})")
                results.append(result)
                write_summary(output_dir, requested_steps, results)
                continue
            if importlib.util.find_spec("music21") is None:
                result = skipped_step_result(index, step_name, output_dir, "music21 is not installed in the current interpreter.")
                print(f"[{index}/{len(requested_steps)}] {step_name}: SKIPPED ({result.log_path})")
                results.append(result)
                write_summary(output_dir, requested_steps, results)
                continue

        result = run_step(index, len(requested_steps), step_name, output_dir)
        results.append(result)
        summary_path = write_summary(output_dir, requested_steps, results)
        if result.status == "failed" and not args.keep_going:
            print(f"Stopping after failed step '{step_name}'. Summary: {summary_path}")
            return result.exit_code or 1

    summary_path = write_summary(output_dir, requested_steps, results)
    overall_failed = any(result.status == "failed" for result in results)
    overall_status = "FAILED" if overall_failed else "PASSED"
    print(f"Validation {overall_status}. Summary: {summary_path}")
    return 1 if overall_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
