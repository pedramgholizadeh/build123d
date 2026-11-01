# AGENTS.md

Guidance for AI coding agents (ZCode, Claude Code, Cursor, Copilot, ...)
working in this repository. Read this before writing code; skim the docs
linked at the bottom before touching the agentic layer.

## What this repository is

A fork of [build123d](https://github.com/gumyr/build123d) — a Python,
parametric BREP CAD library on the OpenCascade kernel (via the `OCP`
bindings) — extended with **`build123d.agentic`**, an add-on layer that
makes build123d usable by AI design agents:

- `spatial_context.py` — measured spatial context (coordinates, bboxes,
  analytic surface equations) for LLM prompts
- `interference.py` — pairwise interference / contact / clearance checks
- `parameters.py` — parameters with epistemic status (measured / specified /
  calculated / estimated / unknown / needs_data)
- `feature_graph.py` — the spatial context graph (features + adjacency /
  joints / constraints / tolerances) with change-impact analysis
- `snippets.py` — parametric part snippets, registry, composition manifests
- `ui_bridge.py` — the manifest + rebuild-and-validate protocol for UIs
- `rag.py` — static AST chunking of CAD code for RAG

The layer is strictly **additive**: it never modifies kernel classes.
Keep it that way unless a task explicitly says otherwise.

## Layout

```
src/build123d/            # the library (topology/, builders, objects, exporters)
src/build123d/agentic/    # the AI-agentic layer (this fork's addition)
tests/                    # pytest suite; test_direct_api/ has per-class unit tests
tests/test_agentic_*.py   # tests for the agentic layer
docs/                     # Sphinx docs; docs/agentic/ is the agentic layer's manual
docs/agentic/spec-kit/    # CAD spec-driven development templates
examples/                 # runnable model scripts
tools/                    # maintainer scripts (not shipped)
```

## Commands

```bash
# environment (python >= 3.11, < 3.15)
python3 -m venv .venv && .venv/bin/pip install -e ".[development]"

# tests (agentic layer only)
.venv/bin/pytest tests/test_agentic_*.py -x -q

# full suite
.venv/bin/pytest tests/ -x -q

# formatting (CI enforces black, line length 88)
.venv/bin/black src/build123d/agentic tests/test_agentic_*.py
```

If `.[development]` fails to resolve (upstream pins occasionally lag),
install the runtime deps explicitly — see `pyproject.toml [project.dependencies]`
— plus `pytest pytest-xdist`, then `pip install --no-deps -e .`.

## The agent loop (how to design things here)

When a task asks you to **design or modify a model** (not just edit library
code), follow the loop; skipping verification means you have typed geometry,
not designed it:

1. **CONTEXT** — `SpatialContext(model).to_markdown()` of the current state.
   Treat its numbers as the only truth about geometry; never re-derive
   coordinates by reading code.
2. **PLAN** — put every number in a `ParameterLedger` with its true status.
   Your guesses are `ESTIMATED`, requirements are `SPECIFIED`, caliper
   values are `MEASURED`. A guessed value used as a fact is a bug you wrote.
3. **BUILD** — prefer `@snippet` parts + `compose()` (provenance manifest)
   or a `ParametricModel` (parameters with ranges). Name every part
   (`shape.label = ...`); unlabeled parts are invisible to the graph.
4. **VERIFY** — `check_interference(assembly)` on every multi-part model
   after every change; `FeatureGraph.impact(node, param=...)` before/after
   changing a parameter; `graph.validate()` before declaring done. `report.ok`
   is the gate — contacts are information, interferences are errors.
5. **REPORT** — hand back `SpatialContext` + `InterferenceReport.to_markdown()`
   + `FeatureGraph.impact().to_markdown()` + the assumption list. The user
   gets evidence, not claims.

## Hard rules

- **Never fake measurements.** If a dimension is unknown, mark it
  `NEEDS_DATA`/`UNKNOWN` in the ledger; do not pick a plausible number and
  present it as real.
- **Never widen a tolerance or weaken a check** to make validation pass.
  Fix the geometry or surface the conflict to the user.
- **No monkey-patching** the kernel; the agentic layer composes, it does not
  override build123d classes.
- **Units** are as-modeled (build123d is unitless); default to mm and state
  the unit in every report and parameter (`unit="mm"`).
- Every agentic-layer feature ships with: the module, tests
  (`tests/test_agentic_*.py`), a doc page (`docs/agentic/*.md`), and an
  entry in `src/build123d/agentic/__init__.py` exports.
- Docstrings: Google style, same voice as neighboring code. The repo's
  recent commit messages are plain, specific and reason-first — follow
  that; conventional-commit prefixes (`feat(scope):`, `docs:`) are used for
  the agentic layer's commits.

## Conventions

- Python >= 3.11, < 3.15; type hints on all public functions.
- black line length 88; no wildcard imports outside `__init__.py`s.
- Tests are fast and hermetic: small boxes/cylinders, no network, no file
  fixtures except `tmp_path`.
- JSON over YAML for machine-readable output; markdown over HTML for
  agent-facing text.

## Where to learn more

- `docs/agentic/overview.md` — the layer's why and map
- `docs/agentic/spatial-context.md`, `interference-check.md`,
  `feature-graph.md`, `snippets.md`, `ui-bridge.md`, `rag-indexing.md`
- `docs/agentic/spec-kit/` — spec → plan → tasks templates for CAD
- `README.md` → "Agentic CAD layer" section
