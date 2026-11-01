# Spec-Kit Integration

Spec-driven development (à la [github/spec-kit](https://github.com/specify/spec-kit))
fits CAD unusually well: an engineering part *already has* a spec culture
(requirements, tolerances, acceptance criteria). These templates adapt that
workflow to build123d + the agentic layer, so an agent designs against a
measurable spec instead of vibes.

Use the `specify` CLI (or any agent) with the templates in this directory:

```
.specify/templates/
├── spec-template.md    # WHAT to build: requirements, geometry, acceptance
├── plan-template.md    # HOW: modeling strategy, parameters, risks
└── tasks-template.md   # ordered implementation tasks with validation gates
```

## The workflow for a part or mechanism

1. **Specify** — fill `spec-template.md`. Every geometry requirement gets a
   number, a unit and a status (`measured`/`specified`/...). Acceptance
   criteria are *measurable* (a dimension to inspect, a clearance to check),
   never adjectives.
2. **Plan** — fill `plan-template.md`: builder/algebra mode choice, the
   parameter set (which become `Parameter`s of a `ParametricModel`), the
   feature-graph relations, and the risks (thin walls, fits, interferences).
3. **Tasks** — fill `tasks-template.md`: small steps, each ending with a
   verification command (`pytest`, `check_interference`, context diff).
4. **Implement** — the agent writes build123d code task by task.
5. **Validate** — the layer's checks are the spec's enforcement:
   - spatial context diff vs. the spec's dimension table
   - `check_interference` for the assembly requirements
   - `FeatureGraph.validate()` for tolerance/constraint consistency
   - `ParameterLedger.to_markdown()` proving which spec values were facts
     and which are still assumptions

## Why this ordering

The classic agentic-CAD failure is geometry-first thinking: the agent starts
modeling and the intent gets reinvented at every step. Spec-first flips it:
the numbers exist before the geometry, the graph mirrors the spec's
couplings, and every check failure maps to a spec clause.

## Copying the templates

Copy the three templates into your repo (e.g. `.specify/templates/`) and
point your agent at them. They are plain markdown with placeholders
(`[PART NAME]`, `[[...]]`) — no tooling required, but they work well with
`specify`'s `/speckit.specify` → `/speckit.plan` → `/speckit.tasks` flow.
