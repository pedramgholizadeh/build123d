# Agentic CAD Layer (`build123d.agentic`)

build123d models are code, so AI agents can write them — but code alone gives
an agent **no space, no consequences and no memory of what depends on what**.
Real agentic CAD failures follow from exactly that:

| Observed failure | Root cause | Layer that fixes it |
|---|---|---|
| The agent "only sees code" — it has no spatial visualization, so volumes, surfaces and lines lose their geometric meaning | Language context holds *statements*, not coordinates | [Spatial Context](spatial-context.md) |
| Nobody notices when one part cuts into another after a dimension change | No non-hallucinating geometry check | [Interference Detection](interference-check.md) |
| Changing one size silently merges with other constraints and "something else comes out" | Language context is a bag of meaning — there is no structure of *what depends on what* | [Feature Graph](feature-graph.md) |
| The model treats its own guessed numbers as engineering facts | Values carry no epistemic status | [Parameters](parameters are documented inside [Feature Graph](feature-graph.md) and [UI Bridge](ui-bridge.md)) |
| The human cannot see or correct intermediate results | No UI contract between agent and user | [UI Bridge](ui-bridge.md) |
| Multi-part models drift apart; part files are not integrated | Parts are code, not addressable, parameterized units | [Snippets](snippets.md) |
| Agents repeat past work; project knowledge is unfindable | Code is not retrieval-indexed | [RAG Indexing](rag-indexing.md) |

## What this layer is

A small, dependency-free add-on package (`build123d.agentic`) plus process
templates. It does **not** modify the CAD kernel. Everything is plain Python
types (dicts, dataclasses, markdown/JSON strings) so any agent framework,
MCP server or UI can consume it.

The intended loop — *physics in the loop*, the architecture validated by
current research on agentic engineering design:

```
        ┌─────────────────────────────────────────────────────┐
        │  1. CONTEXT    SpatialContext(measured geometry)    │
        │  2. PLAN       ParameterLedger + FeatureGraph       │
        │  3. BUILD      snippets / ParametricModel           │
        │  4. VERIFY     check_interference + graph.validate  │
        │  5. REPORT     markdown: context+assumptions+impact │
        └─────────────────────────────────────────────────────┘
              ▲                                   │
              └──────── fix / re-plan ────────────┘
```

The agent proposes; the kernel and the checks decide. An agent that skips
step 4 has not designed anything — it has typed something.

## Quick start

```python
from build123d import Box, Cylinder, Compound, Pos
from build123d.agentic import (
    SpatialContext, check_interference, FeatureGraph,
    ParameterLedger, ParamStatus, EngineeringParameter,
)

# three named parts of a pump
housing = Box(40, 40, 30); housing.label = "housing"
impeller = Cylinder(12, 20); impeller.label = "impeller"
model = Compound(children=[housing, impeller], label="pump")

# 1. give the agent measured space, not code
print(SpatialContext(model).to_markdown())

# 4. verify with real geometry
report = check_interference(model)
print(report.to_markdown())       # housing <-> impeller: INTERFERENCE ...

# structure: what does changing 'bore_diameter' affect?
graph = FeatureGraph.from_model(model)
print(graph.impact("housing", param="bore_diameter").to_markdown())

# knowledge hygiene: separate facts from assumptions
ledger = ParameterLedger()
ledger.set("bore_diameter", 24.0, ParamStatus.MEASURED, source="caliper")
ledger.set("blade_count", 7, ParamStatus.ESTIMATED, source="agent guess")
print(ledger.to_markdown())
```

## Relationship to build123d-mcp

The [build123d-mcp](https://github.com/pzfreo/build123d-mcp) server exposes
build123d as agent *tools* (measure, preview, import, export). This layer
provides the *context and validation payload* those tools can return:
`SpatialContext.to_markdown()` as the measurement response,
`InterferenceReport` as the check response, `FeatureGraph` as the design
state. The two are complementary: MCP is the transport, `agentic` is the
meaning.

## Relationship to spec-kit

For spec-driven development of parts and mechanisms, see
[Spec-Kit Integration](spec-kit/README.md): CAD-specific templates turn a
natural-language spec into geometry requirements with tolerances, then into
build123d implementation tasks validated by this layer.

## Roadmap (extensible by design)

- **Decision-maker model**: rank candidate fixes by graph impact + check
  results (the "3D design decision-maker" idea) — the graph is the substrate.
- **Solver connections**: SymPy Mechanics for kinematics, SciPy for parameter
  fitting/optimization, external FEA for strength — all consume
  `EngineeringParameter` values and return `ParamStatus.CALCULATED` facts.
- **UI frontends**: anything that can render `ParametricModel.manifest()` and
  call `build(**changes)` — no framework lock-in.
- **Parts libraries**: distribute snippet packages; `SnippetRegistry.load()`
  already accepts any directory of snippet files.
