# Agentic CAD Studio

> Problem it solves: the human cannot see or correct intermediate agent
> work — the UI bridge defined the rebuild-and-validate protocol, but
> nothing spoke it visually. The Studio is the reference frontend: drag a
> parameter, the model rebuilds through the same validated `build()` the
> agents use, and the verdict appears as an interactive 3D preview next to
> the checks.

## What it is

A **local, dependency-free web workbench** served straight from
`build123d.agentic.studio` (stdlib `http.server` — no new packages, no CDN
assets, works air-gapped). It hosts any `ParametricModel` mapping:

```python
from build123d.agentic.studio import serve
from build123d.agentic.ui_bridge import Parameter, ParametricModel

# ...define fixture = ParametricModel(...)...
serve({"fixture": fixture, "pump": pump})   # opens http://127.0.0.1:8000
```

or from the shell, with a module exposing `MODELS`:

```bash
python -m build123d.agentic.studio my_models --port 8080
```

## One protocol, two drivers

The Studio is a thin skin over four HTTP endpoints — the same ones an
agent calls:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/models` | GET | manifests of all served models (parameters, ranges, validation flags) |
| `/api/build` | POST | `{model, overrides}` → validated `BuildResult` (+ `stl_url`, `rebuild_ms`) |
| `/api/stl?build=` | GET | binary STL of a cached build (lazy, served from a temp dir) |
| `/api/report?build=` | GET | markdown bundle: spatial context, interference report, graph, mermaid, ledger |

Drag-and-drop and the agent loop cannot diverge: both go through
`POST /api/build`, both get the same errors, warnings and measured
context back.

## The workbench

- **Left rail** — one slider + numeric control per parameter (ranges and
  units come from the manifest); out-of-range and unknown values are
  rejected server-side and shown inline.
- **Center viewport** — a software-rendered 3D preview (binary STL,
  painter's algorithm with backface culling, Lambert shading) over a
  blueprint grid with a Z-up triad and live bounding-box dimensions.
  Drag to orbit, wheel to zoom, double-click to reset. Library-free by
  design — no WebGL stack, works offline.
- **Right panel** — tabs:
  - **Checks**: blocking problems (with an error summary box), the
    interference findings per pair, and the facts-vs-assumptions ledger.
  - **Graph**: the feature graph (markdown + mermaid source).
  - **Context**: the measured spatial context of the current build.
- **Status strip** — rebuild time, triangle count, and the reminder that
  the API is the same one agents use.

A typical loop: drag `bore_d` below the shaft diameter → the model
rebuilds → the panel shows `interference: ... volume=150.8` in red, the
status pill flips to "1 error" → drag back → "ok". Every step measured,
none interpreted.

## Security posture

The server binds `127.0.0.1` by default and the API can rebuild geometry
and write temp files — keep it local. It is a single-user engineering
tool, not a network service. Builds are serialized with a lock because
OCCT modeling is not thread-safe.

## Extending

- New frontends (Jupyter, desktop, VS Code) can reimplement the UI against
  the same endpoints; `ParametricModel.manifest()` is the contract.
- The frontend is three files in `src/build123d/agentic/studio/static/`
  (HTML/CSS/JS) with no build step — fork it freely.
- Agents: call `/api/build` directly, read `errors`/`warnings` like any
  other check, and link humans to the browser view for review.

See `tests/test_agentic_studio.py` for behavior examples.
