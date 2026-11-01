# Feature Graph: the Spatial Context Graph

> Problem it solves: a language model keeps *meaning*, not geometry. When
> one dimension changes it blends into everything else and the design
> quietly becomes something else. The fix: a second, structural memory —
> **nodes are features, edges are the relations between them** (adjacency,
> joints, constraints, tolerances) — plus impact analysis so a change can be
> traced to exactly what it affects.

## Concepts

- **FeatureNode** — one feature: a solid, a sub-assembly, or an abstract
  element (a requirement, a standard). Carries:
  - `params`: engineering parameters, each with an **epistemic status**
    (`measured` / `specified` / `calculated` / `estimated` / `unknown` /
    `needs_data`) — see [Parameters](#parameters-facts-vs-assumptions)
  - `tolerance`: a `Tolerance(nominal, plus, minus)` band
  - `metadata`: material, standard, function, ...
- **Relation** — a typed edge: `ADJACENT` (measured contact), `JOINT`,
  `CONSTRAINT` (dimensional coupling), `CLEARANCE` (deliberate gap),
  `REFERENCE` (soft link). Attributes carry the measured/declared values.

## Quick start

```python
from build123d.agentic import FeatureGraph, RelationType, Tolerance

graph = FeatureGraph()
graph.add_feature("housing", params={"bore_diameter": 24.0},
                  param_status={"bore_diameter": "measured"})
graph.add_feature("cover", params={"bore_diameter": 24.0},
                  param_status={"bore_diameter": "measured"})
graph.add_feature("shaft", params={"diameter": 23.8},
                  param_status={"diameter": "calculated"})

graph.relate("housing", "cover", RelationType.CONSTRAINT, params=["bore_diameter"])
graph.relate("cover", "shaft", RelationType.CLEARANCE, nominal=0.1)

# the question code alone cannot answer:
impact = graph.impact("housing", param="bore_diameter")
print(impact.to_markdown())
# affected: cover  (constraint edge lists 'bore_diameter')
# re-validate: re-run interference checks ...
```

## Building from a model

```python
from build123d import Box, Compound, Location, Pos, RigidJoint
from build123d.agentic import FeatureGraph

body = Box(20, 20, 10); body.label = "body"
cover = Pos(0, 0, 10) * Box(20, 20, 4); cover.label = "cover"
RigidJoint("top", to_part=body, joint_location=Location((0, 0, 10)))
RigidJoint("bottom", to_part=cover, joint_location=Location((0, 0, 0)))
body.joints["top"].connect_to(cover.joints["bottom"])

graph = FeatureGraph.from_model(Compound(children=[body, cover], label="pump"))
# leaf solids -> nodes, measured contact -> ADJACENT edges,
# gaps <= max_clearance -> CLEARANCE edges, bound joints -> JOINT edges
```

## Validation

`graph.validate()` returns issues instead of throwing — an agent can read
and fix them:

- **error**: relation to a missing feature; parameter outside the node's
  tolerance band
- **warning**: duplicate relations; parameters whose status is
  `estimated`/`unknown`/`needs_data` (assumptions still in the design)

## Parameters: facts vs assumptions

Every plain parameter added via `add_feature(..., params={"x": 1.0})`
defaults to **`estimated`** — an unproven number can never pose as a fact.
Mark what you know:

```python
graph.add_feature("housing",
    params={"bore_diameter": 24.0},
    param_status={"bore_diameter": "measured"})   # from a caliper

graph.parameters()          # all node params as a ParameterLedger
ledger.assumption_count     # how many values are still assumptions
ledger.to_markdown()        # the facts-vs-assumptions table
```

| parameter | value | unit | status | source |
|---|---|---|---|---|
| bore_diameter | 24.0 | mm | measured | caliper |
| blade_count | 7 | - | estimated (!) | agent guess |

## Exports

- `graph.to_json()` / `to_dict()` — structured design state (serializable,
  diffable between sessions)
- `graph.to_mermaid()` — render in docs/UIs/GitHub
- `graph.to_markdown()` — compact agent context
- `graph.impact(node, param=...)` → `ImpactResult` — BFS over relations;
  with `param=` it follows only edges that declare that parameter in
  `attrs["params"]`

## Agent workflow guidance

1. Keep one graph per design session; store `to_json()` next to the model
   file and load it back — it is the design's *structural memory*.
2. After changing a parameter, run `impact()` first, then re-run
   [interference checks](interference-check.md) on the affected pairs, then
   `validate()`.
3. Constraints: encode coupling as `RelationType.CONSTRAINT` with
   `params=["shared_name"]` on the edge — that is what makes scoped impact
   analysis work.
4. Tolerances live on nodes; measured clearances live on edges. Do not
   widen a tolerance to make validation pass — that is hallucination with
   extra steps.

See `tests/test_agentic_feature_graph.py` for behavior examples.
