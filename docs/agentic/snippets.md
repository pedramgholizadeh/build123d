# Parametric Part Snippets

> Problem it solves: standard engineering models mix code, formulas and
> numbers — and a multi-part model needs its separate part files integrated.
> The fix: each part is a small, parameterized, **named snippet**; bigger
> models embed snippets like code snippets, with overrides recorded in a
> manifest. The registry doubles as the parts-library connection point.

## Quick start

```python
from build123d import Box, Cylinder
from build123d.agentic import snippet, SnippetRegistry, compose

@snippet("iso_flange", version="1.2",
         params={"dn": {"description": "nominal bore", "minimum": 10, "maximum": 600},
                 "bolts": {"description": "bolt count"}})
def iso_flange(dn: float = 50.0, bolts: int = 4):
    """A flange per the internal standard."""
    ...

# compose a multi-part model from snippets (like pasting snippets into code)
from build123d.agentic import DEFAULT_REGISTRY
composition = compose([("iso_flange", {"dn": 80}), "bearing", "cover"],
                      registry=DEFAULT_REGISTRY, label="pump")
composition.result          # Compound with labeled children
composition.entries         # manifest: which snippet, which params, which label
print(composition.to_markdown())
```

## The registry: your parts library

```python
registry = SnippetRegistry()
registry.load("my_parts/")          # every *.py with @snippet functions
registry.names                      # ['bearing', 'cover', 'iso_flange', ...]
registry.describe("bearing")        # full metadata dict
registry.to_markdown()              # the whole catalog (RAG-friendly)
shape, applied = registry.instantiate("bearing", bore=12.5)
```

- `instantiate` validates overrides: unknown parameters are rejected,
  numeric bounds (`minimum`/`maximum` in the `params=` metadata) are
  enforced — an agent cannot invent a 10-meter flange silently.
- The returned tuple gives both the geometry **and the exact parameter set
  used** — feed `applied` into a `FeatureNode.params` (with statuses!) so
  the built part and the knowledge about it stay one thing.

## Manifest

Every `compose()` records provenance:

```python
[{"label": "iso_flange_0", "snippet": "iso_flange", "version": "1.2",
  "params": {"dn": 80.0, "bolts": 4}}]
```

That manifest is what makes a multi-part model auditable: which version of
which snippet produced this part, with which parameters.

## Rules for snippet authors

1. A snippet is **pure**: same inputs → same geometry, no globals mutated.
2. Return a build123d `Shape` (Part/Solid/Compound all fine).
3. Every parameter gets a default and, where meaningful, bounds + a
   description — the metadata *is* the documentation the agent reads.
4. Set the shape's `label` inside when the part has a canonical name;
   `compose()` fills `snippetname_index` otherwise.
5. Distribute libraries as plain directories of such files — no packaging
   machinery required.

## Relationship to other layers

- Instantiated shapes **carry their parameters** (`shape.parameters`,
  `shape.parameter_status`, `shape.snippet` provenance), so
  `FeatureGraph.from_model()` turns a composed model into a fully labeled,
  fully parameterized graph automatically — no manual bookkeeping.
- `ParametricModel` (see [UI Bridge](ui-bridge.md)) can wrap a snippet-
  composed build function to get the rebuild-and-validate loop.
- `chunk_file()` from [RAG indexing](rag-indexing.md) tags `@snippet`
  functions as `part-snippet` so retrieval prefers them.

See `tests/test_agentic_snippets.py` for behavior examples.
