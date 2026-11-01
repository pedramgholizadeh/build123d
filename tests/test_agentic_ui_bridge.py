"""Tests for the UI bridge (manifest + rebuild-and-validate loop)."""

import json

import pytest

from build123d import Box, Compound, Pos
from build123d.agentic import Parameter, ParametricModel


def _fixture_model(gap: float = 2.0, post_width: float = 4.0) -> Compound:
    """A plate with a post standing on it, separated by `gap`."""
    plate = Box(30, 30, 3)
    post = Pos(0, 0, 3 + gap + post_width / 2) * Box(post_width, post_width, post_width)
    return Compound(children=[plate, post])


@pytest.fixture()
def model() -> ParametricModel:
    return ParametricModel(
        "fixture",
        _fixture_model,
        [
            Parameter(
                "gap",
                2.0,
                minimum=0.0,
                maximum=20.0,
                step=0.5,
                description="clearance under post",
            ),
            Parameter("post_width", 4.0, minimum=2.0, maximum=10.0),
        ],
    )


class TestParameter:
    def test_bounds_validation(self):
        parameter = Parameter("gap", 2.0, minimum=0.0, maximum=20.0)
        assert parameter.validate(5.0) is None
        assert parameter.validate(-1.0) is not None
        assert parameter.validate(25.0) is not None
        assert parameter.validate("wide") is None  # non-numeric skips bounds

    def test_manifest_entry(self):
        entry = Parameter(
            "gap", 2.0, minimum=0.0, maximum=20.0, step=0.5, unit="mm"
        ).to_dict()
        assert entry["default"] == 2.0
        assert entry["minimum"] == 0.0
        assert entry["unit"] == "mm"


class TestParametricModel:
    def test_build_defaults(self, model):
        result = model.build()
        assert result.ok
        assert result.shape is not None
        assert result.params == {"gap": 2.0, "post_width": 4.0}
        assert result.errors == []
        # plate + post touch (gap=2 means the post floats 2mm above? no: post
        # bottom is at 3+2=5, plate top at 3 -> clearance, not contact)
        assert result.interference is not None
        assert result.interference.ok
        assert "Spatial Context" in result.context_markdown

    def test_interference_flagged_as_error(self):
        def colliding(gap: float = -2.0) -> Compound:
            return _fixture_model(gap=gap)

        colliding_model = ParametricModel(
            "colliding",
            colliding,
            [Parameter("gap", -2.0, minimum=-10.0, maximum=0.0)],
        )
        result = colliding_model.build(gap=-4.0)
        assert not result.ok
        assert any("interference" in error for error in result.errors)
        assert result.to_dict()["interference"]["ok"] is False

    def test_unknown_parameter_rejected(self, model):
        result = model.build(bogus=1.0)
        assert not result.ok
        assert any("unknown parameter" in error for error in result.errors)
        assert result.shape is None

    def test_out_of_bounds_rejected(self, model):
        result = model.build(gap=999.0)
        assert not result.ok
        assert any("above maximum" in error for error in result.errors)

    def test_build_exception_surfaced(self):
        def broken(gap: float = 1.0) -> Compound:
            raise RuntimeError("geometry kernel exploded")

        broken_model = ParametricModel("broken", broken, [Parameter("gap", 1.0)])
        result = broken_model.build()
        assert not result.ok
        assert any("build failed" in error for error in result.errors)

    def test_graph_extracted(self, model):
        result = model.build()
        assert result.graph is not None
        assert len(result.graph.nodes) == 2
        assert result.graph.to_markdown()

    def test_manifest(self, model):
        manifest = model.manifest()
        assert manifest["name"] == "fixture"
        names = [parameter["name"] for parameter in manifest["parameters"]]
        assert names == ["gap", "post_width"]
        assert manifest["validation"]["interference"] is True
        assert manifest["validation"]["feature_graph"] is True
        assert "build(**{parameter: value})" in manifest["call"]

    def test_markdown_manifest(self, model):
        text = model.to_markdown()
        assert "# Parametric Model: fixture" in text
        assert "| gap | 2.0 | 0.0..20.0 | mm |" in text

    def test_result_json(self, model):
        result = model.build()
        data = json.loads(result.to_json())
        assert data["ok"] is True
        assert data["interference"]["parts"]
        assert data["graph"]["nodes"]

    def test_checks_can_be_disabled(self):
        bare = ParametricModel(
            "bare",
            _fixture_model,
            [Parameter("gap", 2.0)],
            check_interference=False,
            build_graph=False,
        )
        result = bare.build()
        assert result.ok
        assert result.interference is None
        assert result.graph is None
        assert result.context_markdown  # context always provided


class TestSweep:
    def test_sweep_entries_in_order(self, model):
        report = model.sweep("gap", [0.0, 5.0, 25.0])
        assert [entry.value for entry in report.entries] == [0.0, 5.0, 25.0]
        # 0 -> small clean clearance, 5 -> clean, 25 -> out of bounds
        assert report.entries[0].ok and not report.entries[0].warnings
        assert report.entries[1].ok and not report.entries[1].warnings
        assert not report.entries[2].ok
        assert report.feasible_values == [0.0, 5.0]
        assert not report.all_ok
        assert "| 5.0 | yes |" in report.to_markdown()

    def test_sweep_unknown_parameter(self, model):
        with pytest.raises(ValueError):
            model.sweep("bogus", [1.0])

    def test_sweep_report_serializable(self, model):
        report = model.sweep("gap", [5.0])
        assert report.to_dict()["entries"][0]["ok"] is True


class TestEvaluate:
    @pytest.fixture()
    def collidable(self) -> ParametricModel:
        def collidable(gap: float = 2.0) -> Compound:
            return _fixture_model(gap=gap)

        return ParametricModel(
            "collidable",
            collidable,
            [Parameter("gap", 2.0, minimum=-10.0, maximum=10.0)],
        )

    def test_feasible_candidate_wins(self, collidable):
        report = collidable.evaluate([{"gap": -5.0}, {"gap": 2.0}, {"gap": 99.0}])
        assert report.best is not None
        assert report.best.rank == 1
        assert report.best.result.params["gap"] == 2.0
        assert report.best.result.ok
        assert report.scores[2].result.errors  # the invalid candidate ranks last
        assert "1000*errors" in report.objective

    def test_custom_objective(self, collidable):
        # prefer the largest gap among feasible candidates
        report = collidable.evaluate(
            [{"gap": 1.0}, {"gap": 5.0}],
            objective=lambda result: -result.params["gap"],
        )
        assert report.best.result.params["gap"] == 5.0
        assert report.objective == "custom objective"

    def test_evaluation_markdown_and_dict(self, collidable):
        report = collidable.evaluate([{"gap": 1.0}])
        assert "| 1 |" in report.to_markdown()
        assert report.to_dict()["scores"][0]["rank"] == 1
