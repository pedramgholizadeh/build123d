"""Tests for the agentic spatial context generator."""

import json

import pytest

from build123d import Axis, Box, Compound, Cylinder, GeomType, Pos
from build123d.agentic import (
    SpatialContext,
    diff_contexts,
    shape_facts,
    spatial_context,
)
from build123d.agentic.spatial_context import surface_equation


class TestSolidFacts:
    def test_box_facts(self):
        plate = Box(10, 20, 5)
        plate.label = "plate"
        facts = shape_facts(plate, precision=2)
        assert facts["name"] == "plate"
        assert facts["volume"] == 1000.0
        assert facts["bounding_box"]["max"] == [5.0, 10.0, 2.5]
        assert facts["bounding_box"]["min"] == [-5.0, -10.0, -2.5]
        assert facts["face_count"] == 6
        assert facts["surface_types"]["plane"] == 6
        assert facts["centroid"] == [0.0, 0.0, 0.0]

    def test_summary_detail_skips_surfaces(self):
        plate = Box(10, 20, 5)
        facts = shape_facts(plate, detail="summary")
        assert "volume" not in facts
        assert "surfaces" not in facts
        assert "bounding_box" in facts

    def test_full_detail_lists_every_surface(self):
        plate = Box(10, 20, 5)
        standard = shape_facts(plate, detail="standard")
        full = shape_facts(plate, detail="full")
        assert len(full["surfaces"]) == 6
        assert len(standard["surfaces"]) == 6


class TestSurfaceEquations:
    def test_cylinder_equation(self):
        shaft = Cylinder(5, 10)
        lateral = shaft.faces().filter_by(GeomType.CYLINDER)[0]
        equation = surface_equation(lateral, precision=3)
        assert equation["type"] == "cylinder"
        assert equation["radius"] == 5.0
        assert equation["axis_direction"] == [0.0, 0.0, 1.0]

    def test_plane_equation(self):
        plate = Box(10, 10, 2)
        top = plate.faces().sort_by(Axis.Z)[-1]
        equation = surface_equation(top)
        assert equation["type"] == "plane"
        assert equation["normal"] == [0.0, 0.0, 1.0]


class TestCompoundContext:
    def test_children_and_markdown(self):
        body = Box(30, 30, 10)
        body.label = "body"
        shaft = Pos(0, 0, 15) * Cylinder(3, 20)
        shaft.label = "shaft"
        model = Compound(children=[body, shaft], label="pump")

        facts = shape_facts(model)
        names = [child["name"] for child in facts["children"]]
        assert "body" in names and "shaft" in names

        context = SpatialContext(model)
        markdown = context.to_markdown()
        assert "# Spatial Context: pump" in markdown
        assert "## shaft" in markdown
        assert "cylinder" in markdown

        data = json.loads(context.to_json())
        assert data["name"] == "pump"
        assert data["context"]["source"] == "build123d.agentic.spatial_context"

    def test_spatial_context_function(self):
        model = Compound(children=[Box(10, 10, 10)])
        markdown = spatial_context(model)
        json_text = spatial_context(model, format="json")
        assert "Spatial Context" in markdown
        assert json.loads(json_text)["name"]

    def test_volume_and_total(self):
        body = Box(10, 10, 10)
        body.label = "body"
        model = Compound(children=[body], label="m")
        context = SpatialContext(model)
        assert context.total_volume == pytest.approx(1000.0, abs=1e-6)


class TestContextDiff:
    def test_identical_contexts_diff_to_nothing(self):
        model = Compound(children=[Box(10, 10, 10)], label="m")
        assert diff_contexts(SpatialContext(model), SpatialContext(model)).empty

    def test_dimension_change_is_measured(self):
        small = Compound(children=[Box(10, 10, 10)], label="m")
        big = Compound(children=[Box(10, 10, 20)], label="m")
        diff = diff_contexts(SpatialContext(small), SpatialContext(big))
        assert not diff.empty
        volume = next(c for c in diff.changes if c.field == "volume")
        assert volume.part == "m"
        assert volume.old == 1000.0
        assert volume.new == 2000.0
        assert volume.delta == 1000.0
        bbox = next(c for c in diff.changes if c.field == "bbox.max")
        assert bbox.new[2] == 10.0
        assert "->" in diff.to_markdown()

    def test_added_and_removed_parts(self):
        before = Compound(children=[Box(10, 10, 10)], label="m")
        after_model = Compound(children=[Box(10, 10, 10), Cylinder(2, 4)], label="m")
        diff = diff_contexts(SpatialContext(before), SpatialContext(after_model))
        assert len(diff.added) == 1
        assert not diff.removed
        assert "added parts" in diff.to_markdown()

    def test_accepts_plain_dicts(self):
        model = Compound(children=[Box(5, 5, 5)], label="m")
        data = SpatialContext(model).data
        assert diff_contexts(data, data).empty

    def test_surface_count_change(self):
        plain = Compound(children=[Box(10, 10, 10)], label="m")
        drilled = Compound(children=[Cylinder(2, 12)], label="m")
        diff = diff_contexts(SpatialContext(plain), SpatialContext(drilled))
        fields = {change.field for change in diff.changes}
        assert "surface_types" in fields
