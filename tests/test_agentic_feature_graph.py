"""Tests for the feature graph (spatial context graph)."""

import pytest

from build123d import Box, Compound, Location, Pos, RigidJoint
from build123d.agentic import (
    EngineeringParameter,
    FeatureGraph,
    ParamStatus,
    Relation,
    RelationType,
    Tolerance,
    check_interference,
)


class TestManualGraph:
    def test_add_and_relate(self):
        graph = FeatureGraph()
        graph.add_feature(
            "housing", params={"bore": 25.0}, param_status={"bore": "measured"}
        )
        graph.add_feature("cover")
        graph.relate("housing", "cover", RelationType.CONSTRAINT, params=["bore"])
        assert set(graph.nodes) == {"housing", "cover"}
        assert len(graph.relations) == 1
        assert graph.neighbors("housing") == ["cover"]
        assert graph.neighbors("cover") == ["housing"]

    def test_duplicate_feature_rejected(self):
        graph = FeatureGraph()
        graph.add_feature("housing")
        with pytest.raises(ValueError):
            graph.add_feature("housing")

    def test_relate_unknown_node_rejected(self):
        graph = FeatureGraph()
        graph.add_feature("housing")
        with pytest.raises(ValueError):
            graph.relate("housing", "ghost", RelationType.ADJACENT)

    def test_param_default_status_is_estimated(self):
        graph = FeatureGraph()
        node = graph.add_feature("bracket", params={"width": 40.0})
        assert node.params["width"].status is ParamStatus.ESTIMATED

    def test_param_status_override(self):
        graph = FeatureGraph()
        node = graph.add_feature(
            "bracket", params={"width": 40.0}, param_status={"width": "measured"}
        )
        assert node.params["width"].status is ParamStatus.MEASURED

    def test_engineering_parameter_passthrough(self):
        graph = FeatureGraph()
        parameter = EngineeringParameter("bore", 25.0, ParamStatus.MEASURED)
        node = graph.add_feature("housing", params={"bore": parameter})
        assert node.params["bore"] is parameter


class TestImpact:
    def _graph(self) -> FeatureGraph:
        graph = FeatureGraph()
        graph.add_feature("housing", params={"bore": 25.0})
        graph.add_feature("cover")
        graph.add_feature("shaft")
        graph.add_feature("unrelated")
        graph.relate("housing", "cover", RelationType.CONSTRAINT, params=["bore"])
        graph.relate("cover", "shaft", RelationType.JOINT)
        return graph

    def test_transitive_impact(self):
        impact = self._graph().impact("housing")
        assert impact.affected == ["cover", "shaft"]
        assert len(impact.via) >= 2
        assert "cover" in impact.to_markdown()

    def test_param_scoped_impact(self):
        impact = self._graph().impact("housing", param="bore")
        # the constraint edge lists "bore", the joint edge does not
        assert impact.affected == ["cover"]

    def test_unknown_node(self):
        with pytest.raises(ValueError):
            self._graph().impact("ghost")

    def test_no_coupling(self):
        impact = self._graph().impact("unrelated")
        assert impact.affected == []
        assert "no other features" in impact.to_markdown()


class TestValidation:
    def test_dangling_relation_is_error(self):
        graph = FeatureGraph()
        graph.add_feature("housing")
        graph.relations.append(Relation("housing", "ghost", RelationType.ADJACENT))
        issues = graph.validate()
        assert any(
            issue.severity == "error" and "ghost" in issue.message for issue in issues
        )

    def test_duplicate_relation_warning(self):
        graph = FeatureGraph()
        graph.add_feature("a")
        graph.add_feature("b")
        graph.relate("a", "b", RelationType.JOINT)
        graph.relate("a", "b", RelationType.JOINT)
        assert any(
            issue.severity == "warning" and "duplicate" in issue.message
            for issue in graph.validate()
        )

    def test_tolerance_violation_is_error(self):
        graph = FeatureGraph()
        node = graph.add_feature(
            "bearing_seat",
            params={"diameter": 30.0},
            param_status={"diameter": "measured"},
            tolerance=Tolerance(25.0, plus=0.1, minus=0.1),
        )
        assert node.tolerance is not None
        issues = graph.validate()
        assert any(
            issue.severity == "error" and "outside tolerance" in issue.message
            for issue in issues
        )

    def test_assumption_warning(self):
        graph = FeatureGraph()
        graph.add_feature("bracket", params={"width": 40.0})  # defaults to estimated
        issues = graph.validate()
        assert any(
            issue.severity == "warning" and "estimated" in issue.message
            for issue in issues
        )

    def test_clean_graph_has_no_errors(self):
        graph = FeatureGraph()
        graph.add_feature(
            "a", params={"width": 40.0}, param_status={"width": "specified"}
        )
        graph.add_feature("b")
        graph.relate("a", "b", RelationType.ADJACENT)
        assert graph.validate() == []


class TestTolerance:
    def test_band(self):
        tolerance = Tolerance(25.0, plus=0.2, minus=0.1)
        assert tolerance.contains(25.1)
        assert tolerance.contains(24.9)
        assert not tolerance.contains(25.3)
        assert not tolerance.contains(24.8)


class TestFromModel:
    def test_adjacent_and_joint_edges(self):
        body = Pos(0, 0, 5) * Box(20, 20, 10)  # spans z in [0, 10]
        body.label = "body"
        cover = Pos(0, 0, 12) * Box(20, 20, 4)  # spans z in [10, 14]
        cover.label = "cover"
        # joints sit exactly on the mating plane z=10
        RigidJoint("top", to_part=body, joint_location=Location((0, 0, 10)))
        RigidJoint("bottom", to_part=cover, joint_location=Location((0, 0, 10)))
        body.joints["top"].connect_to(cover.joints["bottom"])

        graph = FeatureGraph.from_model(Compound(children=[body, cover], label="pump"))
        assert set(graph.nodes) == {"body", "cover"}
        kinds = {(rel.source, rel.target, rel.kind) for rel in graph.relations}
        assert any(kind == RelationType.ADJACENT for _, _, kind in kinds)
        assert any(kind == RelationType.JOINT for _, _, kind in kinds)

    def test_far_parts_no_edge(self):
        alpha = Box(10, 10, 10)
        alpha.label = "alpha"
        omega = Pos(100, 0, 0) * Box(10, 10, 10)
        omega.label = "omega"
        graph = FeatureGraph.from_model(Compound(children=[alpha, omega]))
        assert graph.relations == []

    def test_mapping_input(self):
        parts = {"plate": Box(10, 10, 2), "post": Pos(0, 0, 6) * Box(4, 4, 10)}
        graph = FeatureGraph.from_model(parts)
        assert set(graph.nodes) == {"plate", "post"}
        # post sits on plate -> they touch
        assert any(rel.kind == RelationType.ADJACENT for rel in graph.relations)


class TestExports:
    def test_json_roundtrip(self):
        graph = FeatureGraph()
        graph.add_feature(
            "housing", params={"bore": 25.0}, param_status={"bore": "measured"}
        )
        graph.add_feature("cover")
        graph.relate("housing", "cover", RelationType.CONSTRAINT, params=["bore"])
        data = graph.to_dict()
        assert data["nodes"][0]["params"]["bore"]["status"] == "measured"
        assert "CONSTRAINT" in graph.to_json() or "constraint" in graph.to_json()

    def test_mermaid(self):
        graph = FeatureGraph()
        graph.add_feature("housing")
        graph.add_feature("cover")
        graph.relate("housing", "cover", RelationType.JOINT)
        mermaid = graph.to_mermaid()
        assert mermaid.startswith("graph TD")
        assert 'housing["housing (solid)"]' in mermaid
        assert "housing -->|joint| cover" in mermaid

    def test_markdown_lists_assumptions(self):
        graph = FeatureGraph()
        graph.add_feature("bracket", params={"width": 40.0})
        text = graph.to_markdown()
        assert "width=40.0 [estimated]" in text
        assert "assumptions in design: 1" in text

    def test_parameters_ledger(self):
        graph = FeatureGraph()
        graph.add_feature("a", params={"x": 1.0})  # estimated
        graph.add_feature(
            "b", params={"y": EngineeringParameter("y", 2.0, ParamStatus.MEASURED)}
        )
        ledger = graph.parameters()
        assert ledger.assumption_count == 1
        assert ledger.get("y").is_firm
