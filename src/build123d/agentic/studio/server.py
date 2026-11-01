"""
Agentic CAD Studio - local web server

Serves one or more ParametricModels over a tiny stdlib HTTP API so a
browser becomes the human half of the agentic loop: drag a parameter,
the model rebuilds, the checks run, and the result is shown as a 3D
preview next to the interference report, the feature graph and the
spatial context. Agents drive the same endpoints - the UI and the API
are one protocol.

The server is deliberately dependency-free (stdlib http.server) and
binds to 127.0.0.1 by default: it is a local engineering tool, not a
network service.

name: server.py
by:   build123d agentic layer
date: November 1, 2026

desc:
    serve(models, ...) - expose ParametricModels to the Studio web UI
    and to agents: /api/models, /api/build, /api/stl, /api/report.

license:

    Copyright 2026 build123d

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

from __future__ import annotations

import json
import struct
import tempfile
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from build123d import export_stl

from build123d.agentic.ui_bridge import BuildResult, ParametricModel

__all__ = ["StudioHandle", "serve"]

_STATIC_DIR = Path(__file__).parent / "static"
_MAX_CACHED_BUILDS = 32


@dataclass
class StudioHandle:
    """Control surface for a running studio server.

    Attributes:
        url: the base URL (http://127.0.0.1:port).
        host / port: the bound interface.
    """

    url: str
    host: str
    port: int
    _server: ThreadingHTTPServer = field(repr=False)
    _thread: threading.Thread = field(repr=False)

    def shutdown(self) -> None:
        """Stop the server and release the port."""
        self._server.shutdown()
        self._thread.join(timeout=5)

    def wait(self) -> None:
        """Block until the server is stopped (e.g. Ctrl-C elsewhere)."""
        self._thread.join()


class StudioState:
    """Shared state behind the HTTP handler: models and cached builds."""

    def __init__(self, models: Mapping[str, ParametricModel]):
        unknown = [
            name for name, m in models.items() if not isinstance(m, ParametricModel)
        ]
        if unknown:
            raise TypeError(f"not ParametricModel instances: {unknown}")
        self.models = dict(models)
        self.results: dict[str, BuildResult] = {}
        self.order: list[str] = []
        self.stl_paths: dict[str, Path] = {}
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="b3d_studio_"))
        # OCCT modeling is not thread-safe: serialize builds
        self.build_lock = threading.Lock()

    def remember(self, result: BuildResult) -> str:
        """Cache a build result and return its id (oldest evicted)."""
        build_id = uuid.uuid4().hex[:12]
        self.results[build_id] = result
        self.order.append(build_id)
        while len(self.order) > _MAX_CACHED_BUILDS:
            stale = self.order.pop(0)
            self.results.pop(stale, None)
            self.stl_paths.pop(stale, None)
        return build_id

    def stl_bytes(self, build_id: str) -> bytes | None:
        """Binary STL of a cached build, generated on first request."""
        result = self.results.get(build_id)
        if result is None or result.shape is None:
            return None
        if build_id not in self.stl_paths:
            path = self.tmp_dir / f"{build_id}.stl"
            export_stl(result.shape, str(path))
            self.stl_paths[build_id] = path
        return self.stl_paths[build_id].read_bytes()


def _stl_triangle_count(data: bytes) -> int:
    """Triangle count from a binary STL buffer (header check)."""
    if len(data) < 84:
        return 0
    (count,) = struct.unpack("<I", data[80:84])
    return count


class _Handler(BaseHTTPRequestHandler):
    """Requests are dispatched to the StudioState attached on the server."""

    server: ThreadingHTTPServer

    # -- plumbing ---------------------------------------------------------

    @property
    def state(self) -> StudioState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # keep the console quiet; the UI shows status

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    # -- routes -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        route, query = self._route()
        if route == "/":
            self._send_file(_STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif route.startswith("/static/"):
            asset = route[len("/static/") :]
            if asset in _STATIC_TYPES and (_STATIC_DIR / asset).is_file():
                self._send_file(_STATIC_DIR / asset, _STATIC_TYPES[asset])
            else:
                self._send_error_json(404, f"no asset: {asset}")
        elif route == "/api/models":
            self._send_json(
                {"models": [model.manifest() for model in self.state.models.values()]}
            )
        elif route == "/api/stl":
            data = self.state.stl_bytes(query.get("build", ""))
            if data is None:
                self._send_error_json(404, "unknown build id")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif route == "/api/report":
            self._report(query.get("build", ""))
        else:
            self._send_error_json(404, f"no route: {route}")

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        route, _ = self._route()
        if route != "/api/build":
            self._send_error_json(404, f"no route: {route}")
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_error_json(400, "invalid JSON body")
            return
        name = payload.get("model", "")
        model = self.state.models.get(name)
        if model is None:
            self._send_error_json(404, f"unknown model '{name}'")
            return
        overrides = payload.get("overrides") or {}
        if not isinstance(overrides, dict):
            self._send_error_json(400, "'overrides' must be an object")
            return
        started = time.perf_counter()
        with self.state.build_lock:  # OCCT modeling is not thread-safe
            result = model.build(**overrides)
        rebuild_ms = round((time.perf_counter() - started) * 1000, 1)
        build_id = self.state.remember(result)
        data = result.to_dict()
        data.update(
            model=name,
            build_id=build_id,
            rebuild_ms=rebuild_ms,
            stl_url=f"/api/stl?build={build_id}" if result.shape is not None else None,
        )
        self._send_json(data)

    # -- helpers ----------------------------------------------------------

    def _route(self) -> tuple[str, dict[str, str]]:
        """Split the request path into (route, query) with URL decoding."""
        from urllib.parse import parse_qs, urlsplit

        parts = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(parts.query).items()}
        route = parts.path.rstrip("/") or "/"
        return route, query

    def _report(self, build_id: str) -> None:
        result = self.state.results.get(build_id)
        if result is None:
            self._send_error_json(404, "unknown build id")
            return
        graph = result.graph
        ledger = graph.parameters().to_markdown() if graph else ""
        self._send_json(
            {
                "build_id": build_id,
                "context_markdown": result.context_markdown,
                "interference_markdown": (
                    result.interference.to_markdown()
                    if result.interference
                    else "interference checks disabled for this model"
                ),
                "graph_markdown": graph.to_markdown() if graph else "",
                "mermaid": graph.to_mermaid() if graph else "",
                "assumptions_markdown": ledger,
            }
        )


# static file content types (kept out of the handler for readability)
_STATIC_TYPES = {
    "app.js": "text/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
}


def serve(
    models: Mapping[str, ParametricModel],
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
) -> StudioHandle:
    """Serve the Studio web UI for the given models.

    Args:
        models: name -> ParametricModel mapping (order is kept).
        host: bind interface; keep the default 127.0.0.1 - the API can
            rebuild geometry and is meant to be local.
        port: TCP port (0 picks a free port - handy for tests).
        open_browser: open the default browser on the studio URL.

    Returns:
        A StudioHandle; call .shutdown() to stop, .wait() to block.
    """
    state = StudioState(models)

    server = ThreadingHTTPServer((host, port), _Handler)
    server.state = state  # type: ignore[attr-defined]
    thread = threading.Thread(
        target=server.serve_forever, daemon=True, name="b3d-studio"
    )
    thread.start()
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"
    if open_browser:
        webbrowser.open(url)
    return StudioHandle(
        url=url, host=host, port=actual_port, _server=server, _thread=thread
    )
