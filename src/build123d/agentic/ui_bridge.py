"""
UI Bridge: the rebuild-and-validate protocol

The missing half of agentic CAD is a user interface where the human and the
agent meet: the user drags a dimension, the model rebuilds, and every
validation runs before anyone believes the result. This module is the
backend contract for that loop - a manifest a UI can render (parameters,
ranges, units, defaults) and a build() call that returns geometry plus
measurements, interference findings and graph impact, ready to be shown
back to the user.

name: ui_bridge.py
by:   build123d agentic layer
date: November 1, 2026

desc:
    Parameter / ParametricModel / BuildResult: parameter manifests, one-call
    rebuild with automatic interference checking, spatial context and
    validation, so drag-and-drop UIs and agents drive the same loop.

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
from typing import Any, Callable, Mapping, Sequence

from build123d import Compound, Shape

from build123d.agentic.feature_graph import FeatureGraph
from build123d.agentic.interference import InterferenceReport, check_interference
from build123d.agentic.spatial_context import SpatialContext

__all__ = [
    "BuildResult",
    "CandidateScore",
    "EvaluationReport",
    "Parameter",
    "ParametricModel",
    "SweepEntry",
    "SweepReport",
]


@dataclass
class Parameter:
    """One user-adjustable parameter, with the range a UI may offer.

    Attributes:
        name: parameter name (the build function's keyword).
        default: value used when no override is given.
        minimum: smallest allowed value (None = unbounded).
        maximum: largest allowed value (None = unbounded).
        step: suggested increment for sliders (None = free).
        unit: physical unit shown in the UI.
        description: what the parameter controls.
    """

    name: str
    default: float | int | str
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    unit: str = "mm"
    description: str = ""

    def validate(self, value: Any) -> str | None:
        """Check one value against the bounds.

        Returns:
            None when the value is acceptable, otherwise the error message.
        """
        if not isinstance(value, (int, float)):
            return None  # non-numeric values (e.g. material names) skip bounds
        if self.minimum is not None and value < self.minimum:
            return f"{self.name}={value} below minimum {self.minimum}"
        if self.maximum is not None and value > self.maximum:
            return f"{self.name}={value} above maximum {self.maximum}"
        return None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation (the UI manifest entry)."""
        return {
            "name": self.name,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "unit": self.unit,
            "description": self.description,
        }


@dataclass
class BuildResult:
    """Everything a UI (or an agent) needs after one rebuild.

    Attributes:
        ok: True when the model built and every enabled check passed.
        shape: the built shape (None when the build failed).
        params: the parameter values actually used.
        errors: blocking problems (bad input, build failure, interference).
        warnings: non-blocking observations (contacts, assumptions).
        context_markdown: measured spatial context of the built model.
        interference: pairwise interference findings, if checked.
        graph: the feature graph of the built model, if built.
    """

    ok: bool
    shape: Shape | None
    params: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    context_markdown: str = ""
    interference: InterferenceReport | None = None
    graph: FeatureGraph | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation (geometry excluded)."""
        return {
            "ok": self.ok,
            "params": self.params,
            "errors": self.errors,
            "warnings": self.warnings,
            "context_markdown": self.context_markdown,
            "interference": self.interference.to_dict() if self.interference else None,
            "graph": self.graph.to_dict() if self.graph else None,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Render the result as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class SweepEntry:
    """One build of a parameter sweep.

    Attributes:
        value: the swept parameter's value.
        ok: True when the build validated clean.
        errors: blocking problems found at this value.
        warnings: non-blocking observations at this value.
    """

    value: Any
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "value": self.value,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class SweepReport:
    """The result of sweeping one parameter over a range of values.

    Attributes:
        param: the swept parameter name.
        entries: one entry per requested value, in request order.
    """

    param: str
    entries: list[SweepEntry] = field(default_factory=list)

    @property
    def feasible_values(self) -> list[Any]:
        """Values whose build validated clean, in sweep order."""
        return [entry.value for entry in self.entries if entry.ok]

    @property
    def all_ok(self) -> bool:
        """True when every swept value validated clean."""
        return all(entry.ok for entry in self.entries)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "param": self.param,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def to_markdown(self) -> str:
        """Render the sweep as a compact markdown table."""
        lines = [f"# Sweep: {self.param}", "| value | ok | findings |", "|---|---|---|"]
        for entry in self.entries:
            findings = "; ".join(entry.errors + entry.warnings) or "-"
            lines.append(
                f"| {entry.value} | {'yes' if entry.ok else 'NO'} | {findings} |"
            )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()


@dataclass
class CandidateScore:
    """One ranked candidate parameter set.

    Attributes:
        rank: 1 = best.
        score: objective value; lower is better.
        result: the BuildResult of this candidate.
    """

    rank: int
    score: float
    result: BuildResult

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {"rank": self.rank, "score": self.score, "result": self.result.to_dict()}


@dataclass
class EvaluationReport:
    """Ranked candidate parameter sets - the decision-maker's verdict.

    Attributes:
        objective: human-readable description of the objective used.
        scores: candidates sorted best-first, ranks 1..n.
    """

    objective: str
    scores: list[CandidateScore] = field(default_factory=list)

    @property
    def best(self) -> CandidateScore | None:
        """The top-ranked candidate, if any."""
        return self.scores[0] if self.scores else None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "objective": self.objective,
            "scores": [score.to_dict() for score in self.scores],
        }

    def to_markdown(self) -> str:
        """Render the ranking as a compact markdown table."""
        lines = [
            f"# Candidate Evaluation ({self.objective})",
            "| rank | score | ok | params | errors |",
            "|---|---|---|---|---|",
        ]
        for score in self.scores:
            params = ", ".join(
                f"{key}={value}" for key, value in score.result.params.items()
            )
            lines.append(
                f"| {score.rank} | {score.score:g} | {'yes' if score.result.ok else 'NO'} "
                f"| {params} | {'; '.join(score.result.errors) or '-'} |"
            )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()


class ParametricModel:
    """A rebuildable model plus the validation loop around it.

    Wraps a build function whose keywords are parameters. Every
    :meth:`build` call validates the inputs, runs the build, and - for
    multi-part models - runs interference checks and graph extraction, so
    both a drag-and-drop UI and an agent loop drive exactly the same
    physics-in-the-loop cycle.

    Args:
        name: model name.
        build: function taking the parameters as keywords, returning a Shape.
        parameters: the adjustable parameters (must match build's keywords).
        check_interference: run pairwise checks on multi-part results.
        build_graph: extract a FeatureGraph from the result.

    Example:
        >>> from build123d import Box, Cylinder, Compound, Pos
        >>> from build123d.agentic import Parameter, ParametricModel
        >>> def pump(body_h: float = 20.0, bore_d: float = 8.0) -> Compound:
        ...     return Compound(
        ...         children=[Box(30, 30, body_h), Pos(0, 0, body_h) * Cylinder(bore_d / 2, 10)]
        ...     )
        >>> model = ParametricModel(
        ...     "pump", pump,
        ...     [Parameter("body_h", 20.0, minimum=5.0, maximum=100.0),
        ...      Parameter("bore_d", 8.0, minimum=2.0, maximum=20.0)]
        ... )
        >>> result = model.build(body_h=25.0)
        >>> result.ok, result.params
        (True, {'body_h': 25.0, 'bore_d': 8.0})
    """

    def __init__(
        self,
        name: str,
        build: Callable[..., Shape],
        parameters: Sequence[Parameter],
        *,
        check_interference: bool = True,
        build_graph: bool = True,
    ):
        self.name = name
        self.build_fn = build
        self.parameters: dict[str, Parameter] = {
            parameter.name: parameter for parameter in parameters
        }
        self.check_interference = check_interference
        self.build_graph = build_graph

    def build(self, **overrides: Any) -> BuildResult:
        """Rebuild the model with parameter overrides, then validate it.

        Args:
            **overrides: parameter values (must be declared parameters and
                within their bounds).

        Returns:
            A BuildResult; ``ok`` is False with the reasons in ``errors``
            when anything fails. Geometry is only produced when the build
            itself succeeds.
        """
        errors: list[str] = []
        warnings: list[str] = []
        params: dict[str, Any] = {
            name: parameter.default for name, parameter in self.parameters.items()
        }

        for name, value in overrides.items():
            parameter = self.parameters.get(name)
            if parameter is None:
                errors.append(f"unknown parameter '{name}'")
                continue
            message = parameter.validate(value)
            if message:
                errors.append(message)
                continue
            params[name] = value

        if errors:
            return BuildResult(ok=False, shape=None, params=params, errors=errors)

        try:
            shape = self.build_fn(**params)
        except Exception as error:  # noqa: BLE001 - surfaced to the UI, not raised
            return BuildResult(
                ok=False, shape=None, params=params, errors=[f"build failed: {error}"]
            )

        interference: InterferenceReport | None = None
        graph: FeatureGraph | None = None

        if self.check_interference:
            leaves = shape.solids() if isinstance(shape, Compound) else []
            if len(leaves) >= 2:
                interference = check_interference(shape)
                for pair in interference.interferences:
                    errors.append(
                        f"interference: {pair.a} <-> {pair.b} volume={pair.interference_volume}"
                    )
                for pair in interference.contacts:
                    warnings.append(
                        f"contact: {pair.a} <-> {pair.b} area={pair.contact_area}"
                    )
            else:
                interference = None

        if self.build_graph:
            graph = FeatureGraph.from_model(shape)
            warnings.extend(
                issue.message
                for issue in graph.validate()
                if issue.severity == "warning"
            )

        return BuildResult(
            ok=not errors,
            shape=shape,
            params=params,
            errors=errors,
            warnings=warnings,
            context_markdown=SpatialContext(shape).to_markdown(),
            interference=interference,
            graph=graph,
        )

    def sweep(self, param: str, values: Sequence[Any]) -> SweepReport:
        """Build the model at every value of one parameter and validate each.

        The mechanism check from the spec workflow (does the assembly stay
        valid across the full stroke?): out-of-range or invalid values
        produce failed entries, they never stop the sweep.

        Args:
            param: the parameter to vary; must be a declared parameter.
            values: the values to try.

        Returns:
            A SweepReport with one entry per value, in request order.

        Raises:
            ValueError: if the parameter is not declared.
        """
        if param not in self.parameters:
            raise ValueError(f"unknown parameter '{param}'")
        report = SweepReport(param=param)
        for value in values:
            result = self.build(**{param: value})
            report.entries.append(
                SweepEntry(
                    value=value,
                    ok=result.ok,
                    errors=result.errors,
                    warnings=result.warnings,
                )
            )
        return report

    def evaluate(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        objective: Callable[[BuildResult], float] | None = None,
    ) -> EvaluationReport:
        """Rank candidate parameter sets - the decision-maker substrate.

        The agent (or the user) proposes; the builds and their checks
        decide. Every candidate goes through the same :meth:`build`
        validation as any other rebuild, then is scored: lower is better.
        The default objective penalizes errors heavily and warnings
        lightly (``1000*errors + 10*warnings``); pass a custom objective
        (e.g. maximize a clearance, minimize mass) to encode design intent.

        Args:
            candidates: parameter mappings; each is one candidate.
            objective: optional callable mapping a BuildResult to a
                lower-is-better score.

        Returns:
            An EvaluationReport sorted best-first with ranks 1..n.
        """
        description = (
            "custom objective" if objective else "default: 1000*errors + 10*warnings"
        )
        scored: list[tuple[float, int, BuildResult]] = []
        for index, overrides in enumerate(candidates):
            result = self.build(**dict(overrides))
            score = (
                objective(result)
                if objective
                else 1000.0 * len(result.errors) + 10.0 * len(result.warnings)
            )
            scored.append((score, index, result))
        scored.sort(key=lambda item: (item[0], item[1]))
        return EvaluationReport(
            objective=description,
            scores=[
                CandidateScore(rank=rank, score=score, result=result)
                for rank, (score, _, result) in enumerate(scored, start=1)
            ],
        )

    def manifest(self) -> dict[str, Any]:
        """The UI manifest: what to render and how to call back.

        A UI renders one control per parameter (slider between minimum and
        maximum with the given step, or a text field), then calls
        :meth:`build` with the changed parameter and shows ``errors`` /
        ``warnings`` next to the updated preview.
        """
        return {
            "name": self.name,
            "parameters": [
                parameter.to_dict() for parameter in self.parameters.values()
            ],
            "validation": {
                "interference": self.check_interference,
                "feature_graph": self.build_graph,
            },
            "call": f"{self.name}.build(**{{parameter: value}})",
        }

    def to_markdown(self) -> str:
        """Render the manifest as markdown."""
        lines = [
            f"# Parametric Model: {self.name}",
            "| parameter | default | range | unit |",
            "|---|---|---|---|",
        ]
        for parameter in self.parameters.values():
            low = parameter.minimum if parameter.minimum is not None else "-inf"
            high = parameter.maximum if parameter.maximum is not None else "inf"
            lines.append(
                f"| {parameter.name} | {parameter.default} | {low}..{high} | {parameter.unit} |"
            )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()
