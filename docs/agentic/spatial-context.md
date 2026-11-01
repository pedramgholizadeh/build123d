# Spatial Context Generator

> Problem it solves: an agent *only sees the code*. It has no spatial
> visualization, so every volume, surface and line loses its geometric
> meaning. The fix: attach the space to the code — measured coordinates,
> bounding boxes and analytic surface equations, generated from the kernel.

## What it does

`build123d.agentic.spatial_context` walks a shape or assembly and produces a
compact, exact description: every number is **measured by OpenCascade**,
never inferred by a language model. For each named part it reports:

- bounding box corners, volume, surface area, centroid
- face/edge/vertex counts and surface-type census
- **analytic surface equations**: plane (point + normal), cylinder (radius +
  axis), sphere, cone (semi-angle + apex), torus
- joints and (recursively) all children of a compound/assembly

## Quick start

```python
from build123d import Box, Cylinder, Compound, Pos
from build123d.agentic import SpatialContext, spatial_context, shape_facts

body = Box(30, 30, 10); body.label = "body"
shaft = Pos(0, 0, 15) * Cylinder(3, 20); shaft.label = "shaft"
pump = Compound(children=[body, shaft], label="pump")

# markdown for prompts (token-efficient)
print(SpatialContext(pump).to_markdown())

# structured JSON for tools/APIs
SpatialContext(pump).to_json()

# one-liners
spatial_context(pump)                       # markdown
spatial_context(pump, format="json")        # json
shape_facts(pump, detail="summary")         # just the dict
```

## Output example

```markdown
# Spatial Context: pump
(units: as modeled (mm typical), detail: standard)
- bbox: (-15.0, -15.0, -5.0) -> (15.0, 15.0, 25.0)
- volume: 8763.714
- area: 3292.249
- centroid: (0.0, 0.0, 6.56)

## body (Box)
- bbox: (-15.0, -15.0, -5.0) -> (15.0, 15.0, 5.0)
- volume: 8464.609 | area: 2900.0 | centroid: (0.0, 0.0, 0.0)
- surfaces: plane×6, cylinder×1
  - plane point=(-15.0, -15.0, -5.0) normal=(0.0, 0.0, -1.0)
  ...

## shaft (Cylinder)
- bbox: (-3.0, -3.0, 5.0) -> (3.0, 3.0, 25.0)
- volume: 565.487 | area: 433.539 | centroid: (0.0, 0.0, 15.0)
  - cylinder radius=3.0 axis_point=(0.0, 0.0, 5.0) axis_direction=(0.0, 0.0, 1.0)
```

## API

| Function/Class | Purpose |
|---|---|
| `SpatialContext(shape, precision=3, detail=...)` | build once, render many ways |
| `.to_markdown()` | compact prompt-ready text |
| `.to_json(indent=2)` | structured, diffable |
| `.total_volume` | whole-model volume |
| `spatial_context(shape, format=..., detail=...)` | one-shot convenience |
| `shape_facts(shape, detail=...)` | raw dict (JSON-serializable) |
| `surface_equation(face)` | analytic equation of one face |

Detail levels: `"summary"` (identity + bbox only), `"standard"` (default;
analytic surfaces capped at 6 per type to control tokens), `"full"` (every
analytic face — for small, precision-critical parts).

## Agent workflow guidance

1. **Before writing or editing model code**, generate the context of the
   current model and keep it in the working context — it replaces guessing
   coordinates from reading code.
2. **After every build**, regenerate; the diff between two JSON contexts is
   a cheap "what actually changed geometrically" report.
3. Use `precision` deliberately: 3 decimals for design work, 1–2 for large
   assemblies to save tokens.
4. The context is measured in *as-modeled units* (build123d is unitless;
   mm is the convention). Say the unit explicitly to the agent.

See `tests/test_agentic_spatial_context.py` for behavior examples.
