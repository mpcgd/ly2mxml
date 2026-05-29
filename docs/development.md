# Development

## Local Setup

The project targets Python 3.12 or newer.

Install the package in editable mode:

```bash
pip install -e .
```

Install development dependencies as well if you want the full local test workflow:

```bash
pip install -e .[dev]
```

The repository currently depends on:

- `python-ly` for parsing LilyPond projects
- `pytest` for tests
- `music21` for importer-level confidence checks used in the test suite

## Main Commands

Inspect a LilyPond project:

```bash
python -m ly2mxml inspect path/to/score.ly
```

Convert a LilyPond project:

```bash
python -m ly2mxml convert path/to/score.ly -o path/to/output.musicxml
```

Show command help:

```bash
python -m ly2mxml --help
python -m ly2mxml inspect --help
python -m ly2mxml convert --help
```

## Test Layout

### Focused feature tests

`tests/test_convert.py` is the main semantic regression suite. It exercises individual LilyPond features through focused fixtures such as:

- barlines
- transpose
- ottava
- grace-note variants
- cue handling
- tag filtering
- lyrics and lyricsto
- partCombine behavior
- multi-measure rests

### Supporting tests

- `tests/test_loader.py` covers file loading and path resolution behavior.
- `tests/test_adapter.py` covers the parser-facing adapter and include traversal.
- `tests/test_cli.py` covers CLI argument flow and user-facing behavior.
- `tests/test_writer.py` covers MusicXML writer-specific behavior.

### Acceptance sample

`Test Sample/` contains the larger end-to-end sample project used as an acceptance anchor. This is the best place to spot regressions that only appear when multiple supported LilyPond constructs interact.

## Recommended Validation Workflow

Run the focused suite with the known-good interpreter:

```bash
C:\Users\mdespres\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_loader.py tests/test_adapter.py tests/test_cli.py tests/test_convert.py tests/test_writer.py
```

For a repo-local runner that mirrors this workflow and writes untruncated logs
for every step, use:

```bash
C:\Users\mdespres\AppData\Local\Programs\Python\Python312\python.exe tools/validate.py
```

The runner writes per-step logs, a fresh sample export, and `summary.json`
under `.validation/latest/`. It uses the current interpreter, prepends `src/`
to `PYTHONPATH`, and stops on the first failed step by default.

If you want a single full-suite pytest artifact instead of the staged workflow,
run:

```bash
C:\Users\mdespres\AppData\Local\Programs\Python\Python312\python.exe tools/validate.py --step full-tests
```

For a smaller feature-specific slice, use `-k` to target just the relevant tests.

Examples:

```bash
C:\Users\mdespres\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_convert.py -k "transpose or cue or lyricsto" -q
```

After behavior changes, regenerate the sample output explicitly if you are using it as a local inspection target:

```bash
python -m ly2mxml convert "Test Sample/score.ly" -o "Test Sample/score.musicxml"
```

## Fixture Strategy

`tests/conftest.py` exposes one fixture per focused LilyPond sample. The fixtures are intentionally small so a single syntax claim can be backed by one sample and one or more assertions.

When adding support for a new LilyPond construct:

1. Create a small `.ly` sample in `tests/fixtures/`.
2. Add a fixture path in `tests/conftest.py`.
3. Add a focused regression in `tests/test_convert.py` and, if necessary, CLI or writer coverage.
4. Update `docs/syntax-support.md`.

## Documentation Maintenance

The repository documentation is split into:

- `README.md` for install, quickstart, and project overview
- `docs/architecture.md` for contributor-facing system structure
- `docs/development.md` for local setup and testing workflow
- `docs/syntax-support.md` for the LilyPond syntax support matrix

Treat the syntax-support page as a test-backed contract. If a construct is not handled in code and covered by tests, it should not be promoted to the implemented section.

## Comment And Docstring Strategy

This repository now uses:

- module docstrings for first-party Python modules
- class/function docstrings for public and complex entry points
- heavier explanatory comments only in genuinely non-obvious converter or writer logic

Avoid adding line-by-line commentary to trivial helpers. Prefer comments that explain why a conversion phase exists or what invariant a piece of state is maintaining.