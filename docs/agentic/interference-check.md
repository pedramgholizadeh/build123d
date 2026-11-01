# Geometric Interference Detection

> Problem it solves: nobody notices when a changed dimension makes one part
> cut into another. The fix: a fixed, non-hallucinating checker the agent
> (or the UI) runs after **every** change — physics in the loop.

## What it does

`check_interference` classifies every requested pair of parts using real
kernel operations:

| Status | Meaning | How measured |
|---|---|---|
| `interference` | material overlap — the design is broken (or the overlap must be justified as intent) | boolean intersection volume |
| `contact` | parts touch on their boundary | boundary contact query (`Shape.touch`) |
| `clearance` | parts are separated | exact kernel distance (`Shape.distance_to`) |

Bounding boxes prefilter pairs that cannot possibly interact, so whole
assemblies stay cheap.

## Quick start

```python
from build123d import Box, Compound, Pos
from build123d.agentic import check_interference

# either a name -> shape mapping
report = check_interference({
    "housing": Box(40, 40, 30),
    "shaft": Pos(0, 0, 15) * Cylinder(3, 40),
})

# or a Compound/assembly: leaf solids are checked pairwise
model = Compound(children=[housing, shaft], label="pump")
report = check_interference(model)

if not report.ok:
    print(report.to_markdown())     # raise / show to the user
```

## Report

```markdown
# Interference Report (3 parts, 3 pairs checked)
- housing <-> shaft: INTERFERENCE volume=282.743
- housing <-> cover: contact area=1200.0
- cover <-> shaft: clearance 5.0
result: 1 interference(s), 1 contact(s), 1 clearance(s)
ACTION REQUIRED: resolve interferences or justify them as design intent
```

The same data is available structured (`report.to_dict()` / `to_json()`)
and per-pair (`InterferencePair.status`, `.interference_volume`,
`.contact_area`, `.clearance`).

## API

```python
check_interference(
    parts,                    # Mapping[str, Shape] | Shape (Compound)
    precision=3,              # decimals in reports
    only=[("a", "b"), ...],   # optional pair subset
) -> InterferenceReport
```

- `report.ok` — True when nothing interferes (contacts are legal).
- `report.interferences` / `.contacts` / `.clearances` — filtered lists.
- Raises `ValueError` for < 2 parts or unknown names in `only`.

## Agent workflow guidance

1. **After every geometry change**, re-run on the whole affected assembly.
   Never accept an agent's claim of "no collision" without this report.
2. Treat **contact** as information (mates, press fits) and **interference**
   as an error the agent must fix or explicitly justify (e.g. an intended
   interference fit) — in the second case, record the justification in the
   feature graph relation attributes.
3. Use `only=` to scope checks after a local change, and full checks before
   declaring a design finished.
4. Pair with the [Feature Graph](feature-graph.md): `impact()` tells you
   which pairs to re-check after a parameter change.

See `tests/test_agentic_interference.py` for behavior examples.
