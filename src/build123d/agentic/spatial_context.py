"""
Spatial Context Generator

Turn build123d geometry into an exact, token-efficient textual context that
an AI agent can reason over. Language models see code, not space; this module
attaches the space to the code: positions, bounding boxes, analytic surface
equations (planes, cylinders, cones, spheres, tori), volumes, areas and
joints - everything measured from the kernel, never guessed.

name: spatial_context.py
by:   build123d agentic layer
date: November 1, 2026

desc:
    Generate structured (JSON) and markdown spatial descriptions of shapes,
    compounds and assemblies for use as LLM context ("geometry as context").

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
from typing import Any, Literal

from build123d import Face, Shape

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_SurfaceType

__all__ = ["SpatialContext", "shape_facts", "spatial_context"]

#: Amount of surface detail included in the context.
Detail = Literal["summary", "standard", "full"]

#: Maximum analytic surfaces listed per type in "standard" detail.
_MAX_SURFACES_PER_TYPE = 6


def _round(value: float, precision: int) -> float:
    """Round a float for stable, compact output (normalizing -0.0)."""
    return round(float(value), precision) + 0.0


def _gp_xyz(gp_obj: Any, precision: int) -> list[float]:
    """Extract x/y/z from an OCP gp_Pnt or gp_Dir."""
    return [
        _round(gp_obj.X(), precision),
        _round(gp_obj.Y(), precision),
        _round(gp_obj.Z(), precision),
    ]


def _vector_xyz(vector: Any, precision: int) -> list[float]:
    """Extract x/y/z from a build123d Vector."""
    return [
        _round(vector.X, precision),
        _round(vector.Y, precision),
        _round(vector.Z, precision),
    ]


def surface_equation(face: Face, precision: int = 3) -> dict[str, Any]:
    """Extract the analytic equation of a face's underlying surface.

    This is the "spatial equation attached to the code": instead of hoping a
    language model infers a hole is a cylinder, the kernel is asked directly.

    Args:
        face: the face to describe.
        precision: decimal places for numbers.

    Returns:
        dict with a "type" key plus type-specific geometry, e.g.::

            {"type": "cylinder", "radius": 25.0,
             "axis_point": [0, 0, 0], "axis_direction": [0, 0, 1]}

        Non-analytic surfaces (bspline, bezier, ...) report only their type.
    """
    adaptor = BRepAdaptor_Surface(face.wrapped, True)
    surface_type = adaptor.GetType()

    if surface_type == GeomAbs_SurfaceType.GeomAbs_Plane:
        plane = adaptor.Plane()
        axis = plane.Axis()
        return {
            "type": "plane",
            "point": _gp_xyz(axis.Location(), precision),
            "normal": _gp_xyz(axis.Direction(), precision),
        }
    if surface_type == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        cylinder = adaptor.Cylinder()
        axis = cylinder.Axis()
        return {
            "type": "cylinder",
            "radius": _round(cylinder.Radius(), precision),
            "axis_point": _gp_xyz(axis.Location(), precision),
            "axis_direction": _gp_xyz(axis.Direction(), precision),
        }
    if surface_type == GeomAbs_SurfaceType.GeomAbs_Sphere:
        sphere = adaptor.Sphere()
        return {
            "type": "sphere",
            "radius": _round(sphere.Radius(), precision),
            "center": _gp_xyz(sphere.Location(), precision),
        }
    if surface_type == GeomAbs_SurfaceType.GeomAbs_Cone:
        cone = adaptor.Cone()
        axis = cone.Axis()
        return {
            "type": "cone",
            "semi_angle_deg": _round(
                cone.SemiAngle() * 180.0 / 3.141592653589793, precision
            ),
            "apex": _gp_xyz(cone.Apex(), precision),
            "axis_direction": _gp_xyz(axis.Direction(), precision),
        }
    if surface_type == GeomAbs_SurfaceType.GeomAbs_Torus:
        torus = adaptor.Torus()
        axis = torus.Axis()
        return {
            "type": "torus",
            "major_radius": _round(torus.MajorRadius(), precision),
            "minor_radius": _round(torus.MinorRadius(), precision),
            "center": _gp_xyz(axis.Location(), precision),
            "axis_direction": _gp_xyz(axis.Direction(), precision),
        }
    return {"type": face.geom_type.name.lower()}


def _bbox_facts(shape: Shape, precision: int) -> dict[str, Any]:
    """Bounding box of a shape as min/max corners."""
    bbox = shape.bounding_box()
    return {
        "min": _vector_xyz(bbox.min, precision),
        "max": _vector_xyz(bbox.max, precision),
    }


def _joint_facts(shape: Shape) -> dict[str, Any] | None:
    """Describe joints bound to a shape, if any."""
    joints = getattr(shape, "joints", None)
    if not joints:
        return None
    facts: dict[str, Any] = {}
    for label, joint in joints.items():
        connected = getattr(joint, "connected_to", None)
        facts[label] = {
            "type": type(joint).__name__,
            "connected_to": (
                f"{connected.parent.label}:{connected.label}" if connected else None
            ),
        }
    return facts or None


def _shape_name(shape: Shape, fallback: str) -> str:
    """User label of a shape or a fallback name."""
    label = getattr(shape, "label", "")
    return label if label else fallback


def shape_facts(
    shape: Shape,
    *,
    name: str | None = None,
    precision: int = 3,
    detail: Detail = "standard",
    _fallback_name: str = "shape",
) -> dict[str, Any]:
    """Measure a shape and return its facts as a JSON-serializable dict.

    Every number comes from the OpenCascade kernel - the agent is given
    measurements, not the opportunity to guess.

    Args:
        shape: shape (or compound/assembly) to describe.
        name: override the shape's label.
        precision: decimal places for all numbers.
        detail: "summary" (identity + sizes), "standard" (plus analytic
            surface equations, capped per type) or "full" (every face).
        _fallback_name: used when the shape has no label (internal).

    Returns:
        dict of facts; compounds recurse into "children".
    """
    name = name or _shape_name(shape, _fallback_name)
    facts: dict[str, Any] = {
        "name": name,
        "kind": type(shape).__name__,
        "bounding_box": _bbox_facts(shape, precision),
    }
    if detail == "summary":
        return facts

    faces = sorted(shape.faces(), key=lambda f: -f.area)
    facts["face_count"] = len(faces)
    try:
        facts["volume"] = _round(shape.volume, precision)
    except (AttributeError, ValueError):
        pass
    facts["area"] = _round(shape.area, precision)
    try:
        facts["centroid"] = _vector_xyz(shape.center(), precision)
    except (AttributeError, ValueError):
        pass

    equations = [surface_equation(face, precision) for face in faces]
    type_counts: dict[str, int] = {}
    for equation in equations:
        surface_type = equation["type"]
        type_counts[surface_type] = type_counts.get(surface_type, 0) + 1
    facts["surface_types"] = dict(sorted(type_counts.items(), key=lambda kv: -kv[1]))

    if detail == "full":
        selected = [
            equation for equation in equations if equation["type"] in _ANALYTIC_TYPES
        ]
    else:
        per_type: dict[str, int] = {}
        selected = []
        for equation in equations:
            surface_type = equation["type"]
            if (
                surface_type in _ANALYTIC_TYPES
                and per_type.get(surface_type, 0) < _MAX_SURFACES_PER_TYPE
            ):
                per_type[surface_type] = per_type.get(surface_type, 0) + 1
                selected.append(equation)
    if selected:
        facts["surfaces"] = selected

    joints = _joint_facts(shape)
    if joints:
        facts["joints"] = joints

    children = list(getattr(shape, "children", ()) or ())
    if children:
        facts["children"] = [
            shape_facts(
                child,
                precision=precision,
                detail=detail,
                _fallback_name=f"{name}.child_{index}",
            )
            for index, child in enumerate(children)
        ]
    return facts


_ANALYTIC_TYPES = {"plane", "cylinder", "sphere", "cone", "torus"}


class SpatialContext:
    """A measured spatial description of a model, ready for LLM consumption.

    Build once, render many ways. The data is plain JSON so it can be sent to
    an API, written next to the model file, or diffed between builds.

    Args:
        shape: shape or assembly (Compound with children) to describe.
        precision: decimal places for all numbers.
        detail: surface detail level.

    Example:
        >>> from build123d import Box, Cylinder, Compound, Pos
        >>> from build123d.agentic import SpatialContext
        >>> part = Compound(children=[Box(10, 10, 5), Pos(0, 0, 5) * Cylinder(2, 8)])
        >>> print(SpatialContext(part).to_markdown())
    """

    def __init__(
        self,
        shape: Shape,
        *,
        precision: int = 3,
        detail: Detail = "standard",
    ):
        self.detail: Detail = detail
        self.data: dict[str, Any] = shape_facts(
            shape, precision=precision, detail=detail
        )
        self.data["context"] = {
            "units": "as modeled (mm typical)",
            "detail": detail,
            "source": "build123d.agentic.spatial_context",
        }

    @property
    def total_volume(self) -> float | None:
        """Volume of the whole model, if 3D."""
        return self.data.get("volume")

    def to_json(self, indent: int | None = 2) -> str:
        """Render the context as a JSON string."""
        return json.dumps(self.data, indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render the context as compact, token-efficient markdown."""
        lines: list[str] = []
        data = self.data
        lines.append(f"# Spatial Context: {data['name']}")
        context = data.get("context", {})
        meta = ", ".join(f"{key}: {value}" for key, value in context.items())
        lines.append(f"({meta})")

        bbox = data["bounding_box"]
        lines.append(f"- bbox: {tuple(bbox['min'])} -> {tuple(bbox['max'])}")
        for key in ("volume", "area", "centroid", "face_count"):
            if key in data:
                lines.append(f"- {key}: {data[key]}")

        def render(facts: dict[str, Any], depth: int) -> None:
            """Recursively render one shape's facts and its children."""
            pad = "  " * depth
            heading = f"{pad}## {facts['name']} ({facts['kind']})"
            lines.append("")
            lines.append(heading)
            bbox = facts["bounding_box"]
            lines.append(f"{pad}- bbox: {tuple(bbox['min'])} -> {tuple(bbox['max'])}")
            scalars = [key for key in ("volume", "area", "centroid") if key in facts]
            if scalars:
                lines.append(
                    f"{pad}- " + " | ".join(f"{key}: {facts[key]}" for key in scalars)
                )
            surface_types = facts.get("surface_types")
            if surface_types:
                counts = ", ".join(
                    f"{kind}x{count}" for kind, count in surface_types.items()
                )
                lines.append(f"{pad}- surfaces: {counts}")
            for equation in facts.get("surfaces", []):
                parts = [f"{equation['type']}"]
                parts += [
                    f"{key}={value}"
                    for key, value in equation.items()
                    if key not in ("type", "point", "center", "apex", "axis_point")
                    and not isinstance(value, list)
                ]
                for anchor in (
                    "point",
                    "center",
                    "apex",
                    "axis_point",
                    "normal",
                    "axis_direction",
                ):
                    if anchor in equation:
                        parts.append(f"{anchor}={tuple(equation[anchor])}")
                lines.append(f"{pad}  - " + " ".join(parts))
            joints = facts.get("joints")
            if joints:
                rendered = ", ".join(
                    f"{label}:{info['type']}"
                    + (f"->{info['connected_to']}" if info["connected_to"] else "")
                    for label, info in joints.items()
                )
                lines.append(f"{pad}- joints: {rendered}")
            for child in facts.get("children", []):
                render(child, depth + 1)

        for child in data.get("children", []):
            render(child, 0)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()


def spatial_context(
    shape: Shape,
    *,
    format: Literal["markdown", "json"] = "markdown",
    precision: int = 3,
    detail: Detail = "standard",
) -> str:
    """Convenience function: measure a shape and render it as agent context.

    Args:
        shape: shape or assembly to describe.
        format: "markdown" (compact, for prompts) or "json" (structured).
        precision: decimal places for all numbers.
        detail: surface detail level.

    Returns:
        The rendered spatial context.
    """
    context = SpatialContext(shape, precision=precision, detail=detail)
    return context.to_markdown() if format == "markdown" else context.to_json()
