"""
Feature Graph: the Spatial Context Graph

A language model keeps meaning, not geometry: when one dimension changes it
blends into everything else and the design quietly becomes something else.
The feature graph gives the model a second, structural memory - nodes are
features, edges are the relations between them (adjacency, joints,
constraints, tolerances) - so a change can be traced to exactly what it
affects instead of being re-interpreted from scratch.

name: feature_graph.py
by:   build123d agentic layer
date: November 1, 2026

desc:
    FeatureGraph / FeatureNode / Relation: spatial context graph with impact
    analysis (what does changing this parameter touch?), consistency
    validation, assumption tracking and mermaid export.

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
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping

from build123d import Compound, Shape

from build123d.agentic.interference import check_interference, named_parts
from build123d.agentic.parameters import (
    EngineeringParameter,
    ParamStatus,
    ParameterLedger,
)

__all__ = [
    "FeatureGraph",
    "FeatureNode",
    "ImpactResult",
    "Issue",
    "Relation",
    "RelationType",
    "Tolerance",
]


class RelationType(str, Enum):
    """The kinds of edges a feature graph carries.

    ADJACENT: parts touch or mate (measured contact).
    JOINT: parts are connected through a build123d Joint.
    CONSTRAINT: a dimensional or geometric coupling; attrs may name the
        shared parameters so impact analysis can follow them.
    CLEARANCE: a deliberate gap; attrs may carry its nominal value.
    REFERENCE: a soft link, e.g. geometry derived from another feature.
    """

    ADJACENT = "adjacent"
    JOINT = "joint"
    CONSTRAINT = "constraint"
    CLEARANCE = "clearance"
    REFERENCE = "reference"


@dataclass
class Tolerance:
    """A symmetric/asymmetric tolerance band around a nominal value.

    Attributes:
        nominal: the intended value.
        plus: allowed deviation above nominal.
        minus: allowed deviation below nominal.
        unit: physical unit.
    """

    nominal: float
    plus: float = 0.0
    minus: float = 0.0
    unit: str = "mm"

    def contains(self, value: float) -> bool:
        """True when value lies inside the band."""
        return self.nominal - self.minus <= value <= self.nominal + self.plus

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "nominal": self.nominal,
            "plus": self.plus,
            "minus": self.minus,
            "unit": self.unit,
        }


@dataclass
class FeatureNode:
    """One feature of the design: a solid, a sub-assembly, or an abstract
    element (e.g. a requirement) that other features relate to.

    Attributes:
        id: unique name of the feature.
        kind: free-form classifier, e.g. "solid", "compound", "requirement".
        params: the feature's engineering parameters with their status.
        tolerance: dimensional tolerance attached to the feature.
        metadata: free-form attributes (material, standard, function...).
    """

    id: str
    kind: str = "solid"
    params: dict[str, EngineeringParameter] = field(default_factory=dict)
    tolerance: Tolerance | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        data: dict[str, Any] = {"id": self.id, "kind": self.kind}
        if self.params:
            data["params"] = {
                name: param.to_dict() for name, param in self.params.items()
            }
        if self.tolerance:
            data["tolerance"] = self.tolerance.to_dict()
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass
class Relation:
    """A typed, directed edge between two features.

    Attributes:
        source: id of the source node.
        target: id of the target node.
        kind: the relation type.
        attrs: extra data, e.g. {"contact_area": 45.2} for measured adjacency
            or {"params": ["bore_diameter"]} for a dimensional constraint.
    """

    source: str
    target: str
    kind: RelationType
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "attrs": self.attrs,
        }


@dataclass
class ImpactResult:
    """What a parameter change on one node can affect.

    Attributes:
        root: the node where the change was made.
        param: the changed parameter name, if given.
        affected: node ids reachable through relations, BFS order.
        via: the edges traversed as (source, target, kind) tuples.
    """

    root: str
    param: str | None
    affected: list[str] = field(default_factory=list)
    via: list[tuple[str, str, str]] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the impact analysis for agent context."""
        subject = f"{self.param} @ {self.root}" if self.param else self.root
        lines = [f"# Change Impact: {subject}"]
        if not self.affected:
            lines.append("no other features are coupled to this change")
            return "\n".join(lines)
        lines.append(f"affected ({len(self.affected)}): {', '.join(self.affected)}")
        lines.append("paths:")
        lines += [
            f"- {source} -[{kind}]-> {target}" for source, target, kind in self.via
        ]
        lines.append(
            "re-validate: re-run interference checks and constraint checks for the affected features"
        )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()


@dataclass
class Issue:
    """One consistency problem found by graph validation.

    Attributes:
        severity: "error" (must fix) or "warning" (should review).
        message: human/agent readable description.
        node: the node the issue belongs to, if any.
    """

    severity: Literal["error", "warning"]
    message: str
    node: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {"severity": self.severity, "message": self.message, "node": self.node}


class FeatureGraph:
    """The spatial context graph of a design.

    Nodes are features with parameters (each parameter carrying its
    epistemic status), edges are adjacency, joints, constraints, clearances
    and references. The graph answers the question a language model cannot
    answer from code alone: *if this dimension changes, what else must be
    re-checked?*

    Example:
        >>> from build123d.agentic import FeatureGraph, RelationType
        >>> graph = FeatureGraph()
        >>> graph.add_feature("housing", params={"bore": 25.0})
        >>> graph.add_feature("cover")
        >>> graph.relate("housing", "cover", RelationType.CONSTRAINT, params=["bore"])
        >>> impact = graph.impact("housing", param="bore")
        >>> impact.affected
        ['cover']
    """

    def __init__(self) -> None:
        self.nodes: dict[str, FeatureNode] = {}
        self.relations: list[Relation] = []

    # ---- Construction ----

    def add_feature(
        self,
        node_id: str,
        *,
        kind: str = "solid",
        params: Mapping[str, Any] | None = None,
        tolerance: Tolerance | None = None,
        metadata: Mapping[str, Any] | None = None,
        param_status: dict[str, str] | None = None,
    ) -> FeatureNode:
        """Add a feature node.

        Args:
            node_id: unique feature name.
            kind: feature classifier.
            params: plain values (float/str) or EngineeringParameter values.
            param_status: optional {param_name: "measured"|"estimated"|...}
                applied to plain values; defaults to "estimated" so unproven
                numbers can never pose as facts.
            tolerance: dimensional tolerance of the feature.
            metadata: free-form attributes.

        Returns:
            The created FeatureNode.

        Raises:
            ValueError: if a node with this id already exists.
        """
        if node_id in self.nodes:
            raise ValueError(f"feature '{node_id}' already exists")
        node = FeatureNode(
            id=node_id, kind=kind, tolerance=tolerance, metadata=dict(metadata or {})
        )
        for name, value in (params or {}).items():
            if isinstance(value, EngineeringParameter):
                node.params[name] = value
            else:
                status = (param_status or {}).get(name, "estimated")
                node.params[name] = EngineeringParameter(
                    name=name, value=value, status=ParamStatus(status)
                )
        self.nodes[node_id] = node
        return node

    def relate(
        self, source: str, target: str, kind: RelationType, **attrs: Any
    ) -> Relation:
        """Add a directed relation between two existing features.

        Args:
            source: source node id.
            target: target node id.
            kind: relation type.
            **attrs: extra edge attributes.

        Returns:
            The created Relation.

        Raises:
            ValueError: if either endpoint does not exist.
        """
        for node_id in (source, target):
            if node_id not in self.nodes:
                raise ValueError(f"unknown feature '{node_id}'")
        relation = Relation(source=source, target=target, kind=kind, attrs=attrs)
        self.relations.append(relation)
        return relation

    # ---- Queries ----

    def neighbors(self, node_id: str, kind: RelationType | None = None) -> list[str]:
        """Ids of nodes related to node_id (both directions), optionally
        restricted to one relation type."""
        found: list[str] = []
        for relation in self.relations:
            if kind is not None and relation.kind != kind:
                continue
            if relation.source == node_id:
                found.append(relation.target)
            elif relation.target == node_id:
                found.append(relation.source)
        return found

    def impact(self, node_id: str, param: str | None = None) -> ImpactResult:
        """Trace a change through the graph.

        Args:
            node_id: the node whose parameter (or geometry) changes.
            param: optional parameter name; when given, traversal only
                follows edges whose attrs list that parameter.

        Returns:
            ImpactResult listing affected nodes and the paths to them.

        Raises:
            ValueError: if the node does not exist.
        """
        if node_id not in self.nodes:
            raise ValueError(f"unknown feature '{node_id}'")
        result = ImpactResult(root=node_id, param=param)
        visited = {node_id}
        queue: deque[str] = deque([node_id])
        while queue:
            current = queue.popleft()
            for relation in self.relations:
                if relation.source == current:
                    other = relation.target
                elif relation.target == current:
                    other = relation.source
                else:
                    continue
                if param is not None and param not in relation.attrs.get("params", []):
                    # param-scoped traversal only follows edges that declare
                    # the coupling; an unproven edge must not claim impact
                    continue
                if other in visited:
                    continue
                visited.add(other)
                result.affected.append(other)
                result.via.append(
                    (relation.source, relation.target, relation.kind.value)
                )
                queue.append(other)
        return result

    def parameters(self) -> ParameterLedger:
        """All node parameters collected into one ledger."""
        ledger = ParameterLedger()
        for node in self.nodes.values():
            for parameter in node.params.values():
                ledger.define(parameter)
        return ledger

    # ---- Validation ----

    def validate(self) -> list[Issue]:
        """Check the graph for structural and consistency problems.

        Returns:
            A list of Issues (empty when everything is consistent):
            - relations pointing at missing nodes (error)
            - exact duplicate relations (warning)
            - node parameter values outside the node's tolerance band (error)
            - design relying on estimated/unknown parameters (warning)
        """
        issues: list[Issue] = []
        for relation in self.relations:
            for node_id in (relation.source, relation.target):
                if node_id not in self.nodes:
                    issues.append(
                        Issue(
                            "error", f"relation references missing feature '{node_id}'"
                        )
                    )
        seen: set[tuple[str, str, str]] = set()
        for relation in self.relations:
            key = (relation.source, relation.target, relation.kind.value)
            if key in seen:
                issues.append(
                    Issue(
                        "warning",
                        f"duplicate relation {relation.source}->{relation.target} ({relation.kind.value})",
                    )
                )
            seen.add(key)
        for node in self.nodes.values():
            if node.tolerance is not None:
                for parameter in node.params.values():
                    if isinstance(
                        parameter.value, (int, float)
                    ) and not node.tolerance.contains(float(parameter.value)):
                        issues.append(
                            Issue(
                                "error",
                                f"{node.id}.{parameter.name}={parameter.value} outside tolerance "
                                f"{node.tolerance.nominal} +{node.tolerance.plus}/-{node.tolerance.minus}",
                                node=node.id,
                            )
                        )
            for parameter in node.params.values():
                if parameter.is_provisional:
                    issues.append(
                        Issue(
                            "warning",
                            f"{node.id}.{parameter.name} relies on a {parameter.status.value} value "
                            f"({parameter.value}) - confirm before finalizing",
                            node=node.id,
                        )
                    )
        return issues

    # ---- Model extraction ----

    @classmethod
    def from_model(
        cls,
        model: Shape,
        *,
        max_clearance: float = 1.0,
        precision: int = 3,
        param_status: Mapping[str, str] | None = None,
    ) -> FeatureGraph:
        """Build a graph from a compound/assembly (or a mapping of parts).

        The assembly tree's leaves become nodes; measured contacts become
        ADJACENT edges, small gaps become CLEARANCE edges (within
        max_clearance), and bound joints become JOINT edges.

        Args:
            model: Compound with children/joints, or a name->shape mapping.
            max_clearance: gaps larger than this (mm as modeled) create no edge.
            precision: decimals for measured edge attributes.
            param_status: optional {param_name: status} applied when nodes
                carry labeled parameters; defaults keep measurements honest.

        Returns:
            A populated FeatureGraph.
        """
        graph = cls()
        if isinstance(model, Mapping):
            parts = {name: shape for name, shape in model.items()}
        else:
            parts = dict(named_parts(model))

        for name, shape in parts.items():
            labeled_params = {
                param_name: value
                for param_name, value in (
                    getattr(shape, "parameters", {}) or {}
                ).items()
            }
            graph.add_feature(
                name,
                kind=type(shape).__name__.lower(),
                params=labeled_params or None,
                param_status=dict(param_status or {}),
            )

        # joints in a second pass: connect_to may point at features whose
        # node did not exist during the first pass
        for name, shape in parts.items():
            joints = getattr(shape, "joints", None) or {}
            for joint_label, joint in joints.items():
                connected = getattr(joint, "connected_to", None)
                if connected is None:
                    continue
                other_name = (
                    connected.parent.label
                    if getattr(connected.parent, "label", "")
                    else None
                )
                if other_name in parts:
                    graph.relate(
                        name, other_name, RelationType.JOINT, joint=joint_label
                    )

        report = check_interference(parts, precision=precision)
        for pair in report.pairs:
            if pair.status == "contact":
                graph.relate(
                    pair.a,
                    pair.b,
                    RelationType.ADJACENT,
                    contact_area=pair.contact_area,
                )
            elif (
                pair.status == "clearance"
                and pair.clearance is not None
                and pair.clearance <= max_clearance
            ):
                graph.relate(
                    pair.a, pair.b, RelationType.CLEARANCE, measured=pair.clearance
                )
        return graph

    # ---- Export ----

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "relations": [relation.to_dict() for relation in self.relations],
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Render the graph as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_mermaid(self) -> str:
        """Render the graph as a mermaid flowchart (docs, UIs, agents)."""
        lines = ["graph TD"]
        for node in self.nodes.values():
            lines.append(f'    {node.id}["{node.id} ({node.kind})"]')
        for relation in self.relations:
            lines.append(
                f"    {relation.source} -->|{relation.kind.value}| {relation.target}"
            )
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render the graph as compact markdown for agent context."""
        lines = [
            f"# Feature Graph ({len(self.nodes)} features, {len(self.relations)} relations)"
        ]
        for node in self.nodes.values():
            summary = f"- {node.id} ({node.kind})"
            if node.params:
                rendered = ", ".join(
                    f"{name}={param.value} [{param.status.value}]"
                    for name, param in node.params.items()
                )
                summary += f" params: {rendered}"
            if node.tolerance:
                summary += f" tol: {node.tolerance.nominal} +{node.tolerance.plus}/-{node.tolerance.minus}"
            lines.append(summary)
        for relation in self.relations:
            attrs = f" {relation.attrs}" if relation.attrs else ""
            lines.append(
                f"- {relation.source} -[{relation.kind.value}]-> {relation.target}{attrs}"
            )
        ledger = self.parameters()
        if ledger.assumption_count:
            lines.append(
                f"assumptions in design: {ledger.assumption_count} "
                f"({', '.join(p.name for p in ledger.provisional)})"
            )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()
