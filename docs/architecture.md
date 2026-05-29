# Architecture

## Overview

`ly2mxml` is structured as a pipeline that separates LilyPond parsing, semantic conversion, and MusicXML serialization. The codebase does not attempt to preserve LilyPond page layout. Its goal is to preserve a bounded, test-backed set of musical constructs accurately enough for downstream notation tools.

The high-level flow is:

1. Resolve and load LilyPond source files, including includes.
2. Inspect the parsed project to discover assignments, feature usage, and diagnostics.
3. Convert LilyPond AST nodes into an intermediate score model.
4. Serialize that model as MusicXML 4.0.

## Main Pipeline

### 1. Project loading

`src/ly2mxml/loader.py` provides `ProjectLoader`, which resolves entrypoints, normalizes paths, and caches source text. This keeps include resolution and repeated reads deterministic.

### 2. Parser-facing adapter

`src/ly2mxml/frontend/python_ly_adapter.py` wraps `python-ly` and exposes two primary workflows:

- `load_document_tree()` for conversion
- `inspect()` for preflight analysis and CLI inspection output

The adapter is deliberately thin. It is responsible for loading entry and included documents, walking the parser tree, counting commands and contexts, and surfacing parser-facing diagnostics. It is not responsible for final MusicXML semantics.

### 3. Conversion to the internal score model

`src/ly2mxml/converter.py` is the orchestration core.

Its responsibilities include:

- collecting assignments and quote sources
- extracting score metadata
- planning parts and voices from LilyPond staff/context structures
- flattening supported LilyPond syntax into linear voice content
- tracking state such as relative pitch, transposition, cue suppression, removed tags, and duration scaling
- building `Score`, `Part`, `Voice`, `Measure`, and `MusicEvent` objects

This is where most feature support lives. If a LilyPond syntax form is marked supported in the public documentation, there should usually be corresponding handling and tests rooted here.

### 4. Intermediate score model

`src/ly2mxml/model/score.py` defines the internal representation used between conversion and serialization.

The model is intentionally simple:

- `Score` contains metadata, parts, and conversion diagnostics.
- `Part` holds opening staff defaults such as clef, key, time signature, tempo text, and exported voices.
- `Voice` contains measures and export flags such as compressed empty-measure intent.
- `Measure` holds events, timed clef changes, and any explicit right barline.
- `MusicEvent` describes note/rest content, cue/grace state, articulations, ornaments, lyrics, ties, slurs, tuplets, and attached directions.

The model is already LilyPond-aware enough to preserve semantics, but it is simpler than the parser tree and easier for the MusicXML writer to consume.

### 5. MusicXML serialization

`src/ly2mxml/musicxml/writer.py` turns the intermediate score model into MusicXML.

The writer is responsible for:

- creating the `score-partwise` tree
- choosing per-part divisions
- serializing notes, rests, tuplets, directions, lyrics, articulations, ornaments, and barlines
- handling multiple-rest compression
- merging supported partCombine groups back into combined MusicXML parts when requested

The writer should not need to understand the full LilyPond parser tree. It only consumes the resolved intermediate model.

## Public Entry Points

### CLI

`src/ly2mxml/cli.py` exposes two commands:

- `inspect` for parser-facing inspection output
- `convert` for LilyPond-to-MusicXML conversion

### Python API

The main Python entry surface is `LilypondConverter` in `src/ly2mxml/converter.py`.

Key methods:

- `preflight()` inspects the project and returns supported/unsupported feature information plus diagnostics.
- `build_score()` performs the semantic conversion into the intermediate model.
- `convert_file()` runs preflight, builds the score, and writes MusicXML.

## Feature-Support Philosophy

The project is intentionally conservative. Syntax support is documented from real converter handling and tests, not from parser availability alone. The support matrix is split into three categories:

- implemented
- implemented but bounded
- not yet implemented or unsupported

When adding support for new LilyPond syntax, update the converter logic, add tests and fixtures, and then update `docs/syntax-support.md`.

## Acceptance Strategy

The repository uses two complementary validation layers:

- focused fixtures in `tests/fixtures/` that isolate one syntax feature at a time
- the broader project in `Test Sample/` as an acceptance-oriented end-to-end sample

That combination lets the codebase evolve without overclaiming support for syntax that is parseable but not semantically implemented.

## Where To Extend The System

When adding a new LilyPond construct, the usual sequence is:

1. Confirm how `python-ly` represents the syntax in the AST.
2. Extend `LilypondConverter` so the syntax becomes score-model semantics.
3. Extend `MusicXmlWriter` only if the intermediate model needs new MusicXML output.
4. Add or update focused fixtures and tests.
5. Update `docs/syntax-support.md` and any relevant README wording.

If an area starts requiring many cross-cutting edits, that is usually a sign the converter class should be split by responsibility rather than refactored only with smaller helpers.