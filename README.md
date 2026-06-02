# ly2mxml

`ly2mxml` converts LilyPond projects into MusicXML with a focus on preserving musical meaning rather than page layout. It is aimed at LilyPond sources that need to round-trip into applications such as Dorico or MuseScore while keeping notes, rhythm, articulations, dynamics, lyrics, cue handling, and other playback- or notation-relevant semantics.

## Why This Project Exists

This converter is built on top of `python-ly` for parsing LilyPond projects, includes, and variables, but it does not rely on `python-ly` for final MusicXML export. The project uses its own intermediate score model and MusicXML writer so it can control rhythmic correctness and preserve the bounded LilyPond constructs that matter for downstream notation tools.

## Status

The project is intentionally scoped. It supports a growing, test-backed subset of LilyPond syntax rather than claiming full LilyPond compatibility.

- Supported examples are backed by fixtures in `tests/fixtures/` and by the acceptance sample in `Test Sample/`.
- Unsupported or only partially supported syntax is documented explicitly instead of being left implicit.
- The current support matrix is described in `docs/syntax-support.md`.

## Requirements

- Python 3.12 or newer
- `python-ly >= 0.9`

Optional developer tooling:

- `pytest >= 8.2`
- `music21 >= 10.3`

## Installation

Install the package in editable mode for local development:

```bash
pip install -e .
```

Install development dependencies as well if you plan to run tests:

```bash
pip install -e .[dev]
```

## Command Line Usage

The package exposes a `ly2mxml` command with two subcommands.

### Inspect a LilyPond project

```bash
ly2mxml inspect path/to/score.ly
```

This command reports parser-facing information such as:

- included files
- assignments and user variables
- detected supported features
- diagnostics raised during inspection

For machine-readable output:

```bash
ly2mxml inspect path/to/score.ly --json
```

### Convert to MusicXML

```bash
ly2mxml convert path/to/score.ly -o path/to/output.musicxml
```

If `-o` is omitted, the converter writes `<source>.musicxml` next to the LilyPond entrypoint.

Available export options:

- `--partcombine-mode separate` keeps `\partCombine` sources as separate exported parts.
- `--partcombine-mode combined` merges supported `\partCombine` pairs back into one MusicXML part with multiple voices.
- `--include-cues` enables cue-note export. Cue notes are ignored by default.

## Quickstart With The Sample Project

The repository contains an acceptance sample in `Test Sample/score.ly`.

Inspect the sample:

```bash
ly2mxml inspect "Test Sample/score.ly"
```

Convert the sample:

```bash
ly2mxml convert "Test Sample/score.ly" -o "Test Sample/score.musicxml"
```

This sample is the best place to understand the current end-to-end workflow because it uses includes, part combining, dynamics, tuplets, grace notes, and other notation features exercised by the converter.

## Supported LilyPond Surface

The converter currently covers a bounded but practical set of LilyPond syntax, including:

- notes, rests, chords, key signatures, and time signatures
- supported staff clefs, including common mid-staff clef changes
- relative pitch and transposed music
- grace-note handling
- supported dynamics, hairpins, articulations, and trills
- explicit barlines and ottava shifts
- `\repeat unfold`, `\repeat volta`, `\tuplet`, `\times`, and `\scaleDurations`
- quote-based cue extraction via `\addQuote`, `\cueDuring`, `\quoteDuring`, and `\killCues`
- `\addlyrics` and bounded `\lyricsto` support
- bounded `\tag` and `\removeWithTag` support
- bounded `\partCombine` export in separate and combined modes
- compressed full-measure rest export with `\compressEmptyMeasures`

See `docs/syntax-support.md` for the full matrix of implemented, bounded, and not yet implemented LilyPond syntax.

## Known Limitations

This project does not currently aim to cover all of LilyPond. Important current boundaries include:

- unsupported simultaneous voice-level music that requires true polyphonic flattening in one linear voice stream
- repeat forms outside the currently supported unfold and volta handling
- conflicting clef-change schedules across multiple rendered voices in one staff
- general Scheme-driven music evaluation
- broader cue, lyric, and tag semantics outside the currently tested workflows

When in doubt, treat the test suite and `docs/syntax-support.md` as the source of truth.

## Project Structure

- `src/ly2mxml/loader.py` resolves and caches source files.
- `src/ly2mxml/frontend/python_ly_adapter.py` wraps `python-ly` inspection and document loading.
- `src/ly2mxml/converter.py` transforms LilyPond AST nodes into the internal score model.
- `src/ly2mxml/model/score.py` defines the intermediate score dataclasses.
- `src/ly2mxml/musicxml/writer.py` serializes the intermediate model as MusicXML.
- `tests/fixtures/` holds focused LilyPond samples for individual features.
- `Test Sample/` holds the broader acceptance sample project.

## Additional Documentation

- `docs/architecture.md` explains the conversion pipeline and internal model.
- `docs/development.md` covers local setup, tests, and contributor workflow.
- `docs/syntax-support.md` lists implemented, bounded, and not yet implemented LilyPond syntax.

## Testing

Run the focused project suite with the project interpreter:

```bash
python -m pytest tests/test_loader.py tests/test_adapter.py tests/test_cli.py tests/test_convert.py tests/test_writer.py
```

For a repo-local validation run that captures each step to deterministic log
files, use:

```bash
python tools/validate.py
```

The runner writes per-step logs and `summary.json` to `.validation/latest/`.
If you want one unambiguous full-suite pytest log instead of the staged
workflow, run:

```bash
python tools/validate.py --step full-tests
```

## License And Ownership

This repository currently documents the code as-is and does not add a separate license file in this pass.