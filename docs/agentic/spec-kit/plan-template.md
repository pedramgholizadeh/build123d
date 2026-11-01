# Implementation Plan: [PART / MECHANISM NAME]

**Spec:** [link/path to the spec] · **Status:** [draft | review | approved]

## 1. Modeling strategy

- Mode: [builder / algebra / mixed] — and why
- Reuse: existing snippets from [library path] to embed vs. new parts
- Structure: parts list of the model (each becomes a labeled shape or a
  snippet instance)

| Part | Source (new / snippet name) | Label |
|------|------------------------------|-------|
| [housing] | [new, `housing()`] | [housing] |
| [bearing] | [snippet `bearing`] | [bearing_1] |

## 2. Parameter model

The single source of truth for numbers — spec §4 mapped to code parameters:

| Spec ID | Parameter name | Default | Range | Unit | Status |
|---------|----------------|---------|-------|------|--------|
| G-1 | plate_width | 40.0 | 20..100 | mm | specified |
| G-2 | bore_diameter | 24.0 | 8..60 | mm | measured |

These become `Parameter(...)` entries of one `ParametricModel` and
`EngineeringParameter`s (with the same statuses) on the feature-graph nodes.

## 3. Feature graph plan

Nodes and relations to encode (so impact analysis works on day one):

```
housing -[CONSTRAINT params=[bore_diameter]]-> bearing_seat
bearing_seat -[ADJACENT]-> bearing_1
...
```

## 4. Validation plan

Which check enforces which acceptance criterion:

| AC | Check | Where it runs |
|----|-------|---------------|
| AC-1 | SpatialContext dimension diff | test / final report |
| AC-2 | `check_interference` sweep over stroke | pytest |
| AC-3 | min clearance assertion | pytest |
| AC-4 | `FeatureGraph.validate()` == no errors | pytest |

## 5. Risks

| Risk | Signal to watch | Mitigation |
|------|-----------------|------------|
| [thin wall at 2 mm] | [context area/volume drop] | [fillet + re-check] |
| [press fit tolerance] | [contact without interference] | [explicit tolerance on graph] |

## 6. Out of scope

[Explicitly listed non-goals, so the agent does not "helpfully" model them.]
