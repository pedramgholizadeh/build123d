# UI Bridge: the rebuild-and-validate protocol

> Problem it solves: the human cannot see or correct intermediate agent
> work. The fix: the backend contract for a loop where the user drags a
> dimension, the model rebuilds, and **every validation runs before anyone
> believes the result** — drag-and-drop that directly drives the code.

This module is deliberately *only* the backend: any UI (web, desktop, Jupyter)
that can render JSON and call a function can sit on top. No framework, no
server, no lock-in.

## The protocol

**1. Discover** — render controls from the manifest:

```python
model.manifest()
# {"name": "fixture",
#  "parameters": [{"name": "gap", "default": 2.0, "minimum": 0.0,
#                  "maximum": 20.0, "step": 0.5, "unit": "mm",
#                  "description": "clearance under post"}, ...],
#  "validation": {"interference": true, "feature_graph": true},
#  "call": "fixture.build(**{parameter: value})"}
```

**2. Rebuild** — one call per edit (debounce drags):

```python
result = model.build(gap=5.0)
result.ok          # False when anything failed
result.errors      # blocking: bad input, build failure, interferences
result.warnings    # non-blocking: contacts, assumptions in the design
result.shape       # the rebuilt geometry (None on failure)
result.interference    # full InterferenceReport
result.graph           # FeatureGraph of the result
result.context_markdown  # measured spatial context of the new build
```

**3. Show** — the UI renders the rebuilt geometry next to `errors` and
`warnings`; the user fixes what a human fixes best (intent: "that overlap
is a press fit, not a bug") and the agent fixes the rest.

## Quick start

```python
from build123d import Box, Compound, Pos
from build123d.agentic import Parameter, ParametricModel

def fixture(gap: float = 2.0, post_width: float = 4.0) -> Compound:
    plate = Box(30, 30, 3)
    post = Pos(0, 0, 3 + gap + post_width / 2) * Box(post_width, post_width, post_width)
    return Compound(children=[plate, post])

model = ParametricModel(
    "fixture", fixture,
    [Parameter("gap", 2.0, minimum=0.0, maximum=20.0, step=0.5),
     Parameter("post_width", 4.0, minimum=2.0, maximum=10.0)],
)

result = model.build(gap=-1.0)
assert not result.ok
assert any("interference" in e for e in result.errors)   # the loop works
```

## Behavior details

- Unknown parameters and out-of-range values are **rejected before any
  geometry is built** — a UI cannot push the model into a nonsense state.
- Build exceptions are caught and returned in `errors` — the loop survives
  a kernel error.
- Multi-part results (Compounds with ≥ 2 leaf solids) get interference
  checks automatically; interferences become `errors`, contacts become
  `warnings` (contacts are usually design intent — a mate, a press fit).
- `check_interference=False` / `build_graph=False` disable the
  corresponding step for single-part or performance-critical models.
- `result.to_json()` is the whole payload a web backend needs to forward.

## Agent + human, one loop

The same `ParametricModel` serves both sides — that is the point:

- the **agent** calls `build(**changes)` in its tool loop and reads
  `errors`/`warnings`/`context_markdown` like a physics solver's verdict;
- the **user** drags a slider bound to the same manifest and sees the same
  verdicts instantly.

Divergence between "what the agent changed" and "what the user sees" is
impossible because both go through the same call.

## Sweeps and candidate evaluation (the decision-maker)

Two model-level methods turn the loop from "one change at a time" into a
search the physics can arbitrate — the substrate of the 3D design
decision-maker idea:

```python
# mechanism check: is the assembly valid across the whole stroke?
report = model.sweep("gap", [0.0, 1.0, 2.0, 5.0, 10.0])
report.feasible_values          # [0.0, 1.0, 2.0, 5.0, 10.0]
print(report.to_markdown())     # | value | ok | findings |

# the agent proposes several candidates; the checks rank them
evaluation = model.evaluate(
    [{"gap": 1.0}, {"gap": 5.0}, {"gap": 99.0}]
)
evaluation.best.result.params   # {'gap': 5.0}
print(evaluation.to_markdown())
```

- `sweep(param, values)` builds at every value (invalid values become
  failed entries, never exceptions) and reports per-value errors and
  warnings — the AC-style "valid across the full range" acceptance check.
- `evaluate(candidates, objective=None)` runs every candidate through the
  same `build()` validation and ranks them, lower score better. The
  default objective is `1000*errors + 10*warnings`; pass a custom
  objective (minimize mass, maximize a clearance, prefer fewer
  assumptions) to encode design intent. The verdict is a measured
  ranking — never the model's opinion.

See `tests/test_agentic_ui_bridge.py` for behavior examples.
