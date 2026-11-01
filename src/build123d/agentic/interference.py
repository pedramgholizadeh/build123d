"""
Geometric Interference Detection

Pairwise verification that parts of a model do what engineering drawings
promise: overlap (interference), touch (contact) or stay apart (clearance).
An agent that changes one dimension can silently break another part; this
module is the fixed, non-hallucinating checker it should call after every
change - physics in the loop.

name: interference.py
by:   build123d agentic layer
date: November 1, 2026

desc:
    Detect interferences, contacts and clearances between the named parts of
    a model or assembly using OpenCascade booleans and distance queries.

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
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Iterable, Literal, Mapping

from build123d import Compound, Shape

__all__ = ["InterferencePair", "InterferenceReport", "check_interference"]

#: Outcome of checking one pair of parts.
PairStatus = Literal["interference", "contact", "clearance"]

#: Volumes below this are treated as boundary contact, not material overlap.
_VOLUME_EPS = 1e-9


@dataclass
class InterferencePair:
    """The result of checking one pair of named parts.

    Attributes:
        a: name of the first part.
        b: name of the second part.
        status: "interference" (material overlap), "contact" (they touch) or
            "clearance" (they are separated by some distance).
        interference_volume: overlapping material volume in mm³
            (interference only).
        contact_area: touching surface area in mm² (contact only).
        clearance: smallest distance between the parts in mm (clearance only).
    """

    a: str
    b: str
    status: PairStatus
    interference_volume: float | None = None
    contact_area: float | None = None
    clearance: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "a": self.a,
            "b": self.b,
            "status": self.status,
            "interference_volume": self.interference_volume,
            "contact_area": self.contact_area,
            "clearance": self.clearance,
        }


@dataclass
class InterferenceReport:
    """All pairwise checks for a set of parts.

    Attributes:
        pairs: one entry per checked pair.
        parts: names of the parts that were checked.
    """

    pairs: list[InterferencePair] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)

    @property
    def interferences(self) -> list[InterferencePair]:
        """Pairs with material overlap."""
        return [pair for pair in self.pairs if pair.status == "interference"]

    @property
    def contacts(self) -> list[InterferencePair]:
        """Pairs that touch without overlapping."""
        return [pair for pair in self.pairs if pair.status == "contact"]

    @property
    def clearances(self) -> list[InterferencePair]:
        """Pairs kept apart."""
        return [pair for pair in self.pairs if pair.status == "clearance"]

    @property
    def ok(self) -> bool:
        """True when no pair interferes."""
        return not self.interferences

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "parts": self.parts,
            "ok": self.ok,
            "pairs": [pair.to_dict() for pair in self.pairs],
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Render the report as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render the report as compact markdown for agent context or logs."""
        lines = [
            f"# Interference Report ({len(self.parts)} parts, {len(self.pairs)} pairs checked)"
        ]
        for pair in self.pairs:
            if pair.status == "interference":
                lines.append(
                    f"- {pair.a} <-> {pair.b}: INTERFERENCE volume={pair.interference_volume}"
                )
            elif pair.status == "contact":
                lines.append(
                    f"- {pair.a} <-> {pair.b}: contact area={pair.contact_area}"
                )
            else:
                lines.append(f"- {pair.a} <-> {pair.b}: clearance {pair.clearance}")
        lines.append(
            f"result: {len(self.interferences)} interference(s), "
            f"{len(self.contacts)} contact(s), {len(self.clearances)} clearance(s)"
        )
        if not self.ok:
            lines.append(
                "ACTION REQUIRED: resolve interferences or justify them as design intent"
            )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()


def _tree_leaves(shape: Shape) -> list[Shape]:
    """Leaf nodes of a shape's assembly tree (children of compounds)."""
    children = getattr(shape, "children", ()) or ()
    if not children:
        return [shape]
    leaves: list[Shape] = []
    for child in children:
        leaves += _tree_leaves(child)
    return leaves


def _ancestor_label(shape: Shape) -> str:
    """Nearest labeled label on the path to the root, if any."""
    node = getattr(shape, "parent", None)
    while node is not None:
        label = getattr(node, "label", "")
        if label:
            return label
        node = getattr(node, "parent", None)
    return ""


def named_parts(parts: Mapping[str, Shape] | Shape) -> list[tuple[str, Shape]]:
    """Normalize input to a list of (name, shape) pairs.

    Accepts a name->shape mapping, or a single shape whose tree leaves
    become the parts (named by their own label, the nearest labeled
    ancestor, or an index - in that order, deduplicated).
    """
    if isinstance(parts, Mapping):
        return list(parts.items())
    shape = parts
    if isinstance(shape, Compound):
        leaves = _tree_leaves(shape)
        if len(leaves) > 1:
            root = getattr(shape, "label", "") or "model"
            names: list[str] = []
            named: list[tuple[str, Shape]] = []
            for index, leaf in enumerate(leaves):
                name = leaf.label or _ancestor_label(leaf) or f"{root}_{index}"
                while name in names:  # two unlabeled leaves may share an ancestor
                    name = f"{name}_{index}"
                names.append(name)
                named.append((name, leaf))
            return named
    return [(getattr(shape, "label", "") or "part", shape)]


# backwards-compatible alias
_named_parts = named_parts


def check_interference(
    parts: Mapping[str, Shape] | Shape,
    *,
    precision: int = 3,
    only: Iterable[tuple[str, str]] | None = None,
) -> InterferenceReport:
    """Check every requested pair of parts for interference, contact or clearance.

    Each pair is checked with real geometry: bounding boxes prefilter pairs
    that cannot interact, OpenCascade booleans measure material overlap, and
    a kernel distance query measures clearance. No estimates, no guesses.

    Args:
        parts: name->shape mapping, or a single Compound whose parts (tree
            leaves) are checked against each other.
        precision: decimal places for volumes, areas and clearances.
        only: optional subset of pairs (names must match the input names).

    Returns:
        InterferenceReport over all checked pairs.

    Raises:
        ValueError: if fewer than two parts are given or an unknown name is
            used in ``only``.

    Example:
        >>> from build123d import Box, Pos
        >>> from build123d.agentic import check_interference
        >>> report = check_interference(
        ...     {"body": Box(10, 10, 10), "pin": Pos(0, 0, 5) * Box(2, 2, 20)}
        ... )
        >>> report.ok
        False
    """
    named = _named_parts(parts)
    if len(named) < 2:
        raise ValueError("interference checks need at least two parts")
    names = {name for name, _ in named}
    shapes = dict(named)

    if only is None:
        checked_pairs = list(combinations(sorted(names), 2))
    else:
        checked_pairs = []
        for first, second in only:
            if first not in names or second not in names:
                raise ValueError(f"unknown part name in 'only': {first}/{second}")
            checked_pairs.append(tuple(sorted((first, second))))

    results: list[InterferencePair] = []
    for first, second in checked_pairs:
        results.append(
            _check_pair(shapes[first], shapes[second], first, second, precision)
        )
    return InterferenceReport(pairs=results, parts=sorted(names))


def _check_pair(
    first: Shape, second: Shape, first_name: str, second_name: str, precision: int
) -> InterferencePair:
    """Classify one pair: interference, contact or clearance."""

    def rnd(value: float) -> float:
        return round(value, precision)

    # cheap prefilter: boxes that cannot meet are pure clearance
    if first.bounding_box().disjoint(second.bounding_box()):
        return InterferencePair(
            a=first_name,
            b=second_name,
            status="clearance",
            clearance=rnd(first.distance_to(second)),
        )

    overlap = first.intersect(second)
    volume = sum(
        result.volume
        for result in overlap
        if result.volume and result.volume > _VOLUME_EPS
    )
    if volume > _VOLUME_EPS:
        return InterferencePair(
            a=first_name,
            b=second_name,
            status="interference",
            interference_volume=rnd(volume),
        )

    touched = first.touch(second)
    if touched:
        return InterferencePair(
            a=first_name,
            b=second_name,
            status="contact",
            contact_area=rnd(sum(item.area for item in touched if item.area)),
        )

    return InterferencePair(
        a=first_name,
        b=second_name,
        status="clearance",
        clearance=rnd(first.distance_to(second)),
    )
