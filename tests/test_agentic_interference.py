"""Tests for the agentic interference detector."""

import pytest

from build123d import Box, Compound, Pos
from build123d.agentic import check_interference


def _named(**parts):
    return {name: shape for name, shape in parts.items()}


class TestPairClassification:
    def test_interference(self):
        base = Box(10, 10, 10)
        intruder = Pos(5, 0, 0) * Box(10, 10, 10)
        report = check_interference(_named(base=base, intruder=intruder))
        pair = report.pairs[0]
        assert pair.status == "interference"
        assert pair.interference_volume == pytest.approx(500.0, abs=1.0)
        assert not report.ok
        assert "INTERFERENCE" in report.to_markdown()
        assert "ACTION REQUIRED" in report.to_markdown()

    def test_contact(self):
        base = Box(10, 10, 10)
        cover = Pos(10, 0, 0) * Box(10, 10, 10)
        report = check_interference(_named(base=base, cover=cover))
        pair = report.pairs[0]
        assert pair.status == "contact"
        assert pair.contact_area == pytest.approx(100.0, abs=1.0)
        assert report.ok  # contact is not interference

    def test_clearance(self):
        base = Box(10, 10, 10)
        distant = Pos(30, 0, 0) * Box(10, 10, 10)
        report = check_interference(_named(base=base, distant=distant))
        pair = report.pairs[0]
        assert pair.status == "clearance"
        assert pair.clearance == pytest.approx(20.0, abs=0.5)

    def test_containment_is_interference(self):
        outer = Box(20, 20, 20)
        inner = Box(5, 5, 5)
        report = check_interference(_named(outer=outer, inner=inner))
        assert report.pairs[0].status == "interference"
        assert report.pairs[0].interference_volume == pytest.approx(125.0, abs=1.0)


class TestReportShape:
    def test_multiple_parts_sorted_pairs(self):
        parts = _named(
            alpha=Box(10, 10, 10),
            beta=Pos(30, 0, 0) * Box(10, 10, 10),
            gamma=Pos(60, 0, 0) * Box(10, 10, 10),
        )
        report = check_interference(parts)
        assert report.parts == ["alpha", "beta", "gamma"]
        assert len(report.pairs) == 3
        assert [pair.status for pair in report.pairs] == ["clearance"] * 3
        assert report.ok

    def test_only_subset(self):
        parts = _named(
            alpha=Box(10, 10, 10),
            beta=Pos(30, 0, 0) * Box(10, 10, 10),
            gamma=Pos(60, 0, 0) * Box(10, 10, 10),
        )
        report = check_interference(parts, only=[("alpha", "gamma")])
        assert len(report.pairs) == 1
        assert {report.pairs[0].a, report.pairs[0].b} == {"alpha", "gamma"}

    def test_json_roundtrip(self):
        parts = _named(base=Box(10, 10, 10), far=Pos(50, 0, 0) * Box(10, 10, 10))
        report = check_interference(parts)
        assert report.to_dict()["ok"] is True
        assert "clearance" in report.to_json()

    def test_too_few_parts(self):
        with pytest.raises(ValueError):
            check_interference(_named(only_one=Box(10, 10, 10)))

    def test_unknown_only_name(self):
        parts = _named(alpha=Box(10, 10, 10), beta=Pos(30, 0, 0) * Box(10, 10, 10))
        with pytest.raises(ValueError):
            check_interference(parts, only=[("alpha", "delta")])


class TestCompoundInput:
    def test_leaf_solids_checked(self):
        body = Box(10, 10, 10)
        body.label = "body"
        overlap = Pos(5, 0, 0) * Box(10, 10, 10)
        overlap.label = "overlap"
        model = Compound(children=[body, overlap], label="pump")
        report = check_interference(model)
        assert len(report.pairs) == 1
        assert report.pairs[0].status == "interference"
        assert "body" in report.parts and "overlap" in report.parts
