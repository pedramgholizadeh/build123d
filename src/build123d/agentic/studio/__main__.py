"""
Command line entry point: serve a module's ParametricModels.

    python -m build123d.agentic.studio my_models [--attr MODELS]
           [--port 8000] [--host 127.0.0.1] [--no-browser]

The module must expose its models as either:
- a dict named MODELS (or the --attr value): {"name": ParametricModel}
- plain module-level ParametricModel variables

Exit code 1 with a listing when no models are found.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from build123d.agentic.studio.server import serve
from build123d.agentic.ui_bridge import ParametricModel


def _collect_models(module: object, attr: str | None) -> dict[str, ParametricModel]:
    """Find the models a module exposes (explicit attr, MODELS, or vars)."""
    candidates = module.__dict__  # type: ignore[attr-defined]
    if attr:
        if attr not in candidates:
            raise SystemExit(f"module has no attribute '{attr}'")
        declared = candidates[attr]
        if not isinstance(declared, dict):
            raise SystemExit(f"'{attr}' must be a dict of name -> ParametricModel")
        return dict(declared)
    if isinstance(candidates.get("MODELS"), dict):
        return dict(candidates["MODELS"])
    found = {
        name: value
        for name, value in candidates.items()
        if not name.startswith("_") and isinstance(value, ParametricModel)
    }
    return found


def main(argv: list[str] | None = None) -> int:
    """Run the studio for one module's models."""
    parser = argparse.ArgumentParser(
        prog="python -m build123d.agentic.studio",
        description="Serve the Agentic CAD Studio for a module's ParametricModels.",
    )
    parser.add_argument("module", help="module path, e.g. my_models or pkg.my_models")
    parser.add_argument(
        "--attr",
        default=None,
        help="attribute holding the models dict (default: MODELS or scan)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    module = importlib.import_module(args.module)
    models = _collect_models(module, args.attr)
    if not models:
        print(
            f"no ParametricModel found in '{args.module}' - define MODELS = "
            "{{'name': ParametricModel(...)}} or module-level models",
            file=sys.stderr,
        )
        return 1
    print(f"models: {', '.join(models)}")
    handle = serve(
        models,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
    )
    print(f"Agentic CAD Studio on {handle.url}  (Ctrl-C to stop)")
    try:
        handle.wait()
    except KeyboardInterrupt:
        handle.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
