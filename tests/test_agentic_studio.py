"""Tests for the Agentic CAD Studio server (stdlib HTTP, localhost)."""

import json
import struct
import urllib.error
import urllib.request

import pytest

from build123d import Box, Compound, Pos
from build123d.agentic.studio import serve
from build123d.agentic.studio.server import StudioState, _stl_triangle_count
from build123d.agentic.ui_bridge import Parameter, ParametricModel


def _fixture_model(gap: float = 2.0, post_width: float = 4.0) -> Compound:
    """Plate with a floating post, `gap` mm above the plate's top face."""
    plate = Box(30, 30, 3)
    post = Pos(0, 0, 3 + gap + post_width / 2) * Box(post_width, post_width, post_width)
    return Compound(children=[plate, post])


@pytest.fixture()
def studio():
    model = ParametricModel(
        "fixture",
        _fixture_model,
        [Parameter("gap", 2.0, minimum=-10.0, maximum=10.0)],
    )
    handle = serve({"fixture": model}, host="127.0.0.1", port=0, open_browser=False)
    yield handle
    handle.shutdown()


def _get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read()


def _get_json(url: str) -> tuple[int, dict]:
    status, data = _get(url)
    return status, json.loads(data)


def _post(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read())


class TestStudioServer:
    def test_index_served(self, studio):
        status, body = _get(studio.url + "/")
        assert status == 200
        assert b"Agentic CAD Studio" in body

    def test_static_assets_served(self, studio):
        _, app_js = _get(studio.url + "/static/app.js")
        _, style = _get(studio.url + "/static/style.css")
        assert b"parseStl" in app_js
        assert b"--accent" in style

    def test_models_manifest(self, studio):
        _, payload = _get_json(studio.url + "/api/models")
        names = [model["name"] for model in payload["models"]]
        assert names == ["fixture"]
        assert payload["models"][0]["parameters"][0]["name"] == "gap"

    def test_build_roundtrip(self, studio):
        status, payload = _post(
            studio.url + "/api/build", {"model": "fixture", "overrides": {"gap": 5.0}}
        )
        assert status == 200
        assert payload["ok"] is True
        assert payload["params"]["gap"] == 5.0
        assert payload["stl_url"]
        assert payload["rebuild_ms"] >= 0

    def test_build_interference_flagged(self, studio):
        _, payload = _post(
            studio.url + "/api/build", {"model": "fixture", "overrides": {"gap": -4.0}}
        )
        assert payload["ok"] is False
        assert any("interference" in error for error in payload["errors"])

    def test_unknown_model_and_routes(self, studio):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _post(studio.url + "/api/build", {"model": "ghost", "overrides": {}})
        assert exc.value.code == 404
        with pytest.raises(urllib.error.HTTPError):
            _get(studio.url + "/api/nothing")

    def test_stl_binary(self, studio):
        _, build = _post(
            studio.url + "/api/build", {"model": "fixture", "overrides": {}}
        )
        status, data = _get(studio.url + build["stl_url"])
        assert status == 200
        (count,) = struct.unpack("<I", data[80:84])
        assert count > 0
        # binary STL: 84-byte header plus exactly 50 bytes per triangle
        assert len(data) == 84 + count * 50
        assert _stl_triangle_count(data) == count

    def test_report_bundle(self, studio):
        _, build = _post(
            studio.url + "/api/build", {"model": "fixture", "overrides": {}}
        )
        _, report = _get_json(studio.url + f"/api/report?build={build['build_id']}")
        assert "Spatial Context" in report["context_markdown"]
        assert "Interference Report" in report["interference_markdown"]
        assert "Feature Graph" in report["graph_markdown"]
        assert report["mermaid"].startswith("graph TD")

    def test_stl_unknown_build_404(self, studio):
        with pytest.raises(urllib.error.HTTPError):
            _get(studio.url + "/api/stl?build=missing")


class TestStudioState:
    def test_rejects_non_models(self):
        with pytest.raises(TypeError):
            StudioState({"bad": "not a model"})

    def test_evicts_oldest_builds(self):
        model = ParametricModel("fixture", _fixture_model, [Parameter("gap", 2.0)])
        state = StudioState({"fixture": model})
        ids = [state.remember(model.build()) for _ in range(40)]
        assert len(state.results) <= 32
        assert ids[0] not in state.results
        assert ids[-1] in state.results
