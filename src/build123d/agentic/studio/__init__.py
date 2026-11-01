"""
build123d.agentic.studio - the Agentic CAD Studio web UI

A local, dependency-free web workbench for ParametricModels: drag a
parameter, the model rebuilds through the same validated build() the
agents use, and the result appears as an interactive 3D preview next
to the interference report, feature graph, spatial context and the
facts-vs-assumptions ledger.

    from build123d.agentic.studio import serve
    serve({"fixture": model})            # opens http://127.0.0.1:8000

or, with a module defining MODELS (a name -> ParametricModel dict):

    python -m build123d.agentic.studio my_models --port 8080

The same HTTP API (/api/models, /api/build, /api/stl, /api/report)
serves agents, so the UI and the agent loop are one protocol.
"""

from build123d.agentic.studio.server import StudioHandle, serve

__all__ = ["StudioHandle", "serve"]
