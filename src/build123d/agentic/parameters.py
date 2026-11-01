"""
Engineering Parameters with Epistemic Status

An agent designing or reverse-engineering a part produces numbers of very
different quality: some were measured, some were specified by the customer,
some were calculated, and some are the model's own estimates. A language
model happily writes an estimated value and later treats it as fact. This
module makes that impossible: every parameter carries its epistemic status,
and reports separate facts from assumptions.

name: parameters.py
by:   build123d agentic layer
date: November 1, 2026

desc:
    EngineeringParameter / ParameterLedger: parameter values tagged with
    measured / specified / calculated / estimated / unknown status, plus
    fact-vs-assumption reports for agent context.

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
from enum import Enum
from typing import Any

__all__ = ["EngineeringParameter", "ParamStatus", "ParameterLedger"]


class ParamStatus(str, Enum):
    """How well a parameter value is known.

    MEASURED values come from physical evidence (calipers, a reference model,
    a photo with a scale). SPECIFIED values are requirements. CALCULATED
    values follow from engineering computation. ESTIMATED values are the
    agent's provisional guesses. UNKNOWN values are missing. NEEDS_DATA
    values cannot be resolved without further input.
    """

    MEASURED = "measured"
    SPECIFIED = "specified"
    CALCULATED = "calculated"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"
    NEEDS_DATA = "needs_data"


#: Statuses an agent may rely on as engineering facts.
_FIRM_STATUSES = {ParamStatus.MEASURED, ParamStatus.SPECIFIED, ParamStatus.CALCULATED}


@dataclass
class EngineeringParameter:
    """One design parameter and how well it is known.

    Attributes:
        name: parameter name, e.g. "shaft_diameter".
        value: the current value (numeric, or a string for material choices).
        status: epistemic status of the value.
        unit: physical unit, e.g. "mm" or "rpm" ("-" for dimensionless).
        source: where the value came from, e.g. "caliper on input shaft".
        note: free-form context, e.g. "assumes H7 fit".

    Example:
        >>> dia = EngineeringParameter("shaft_diameter", 12.0, ParamStatus.MEASURED,
        ...                            source="caliper on input shaft")
        >>> dia.is_firm
        True
    """

    name: str
    value: float | str | None
    status: ParamStatus
    unit: str = "mm"
    source: str = ""
    note: str = ""

    @property
    def is_firm(self) -> bool:
        """True when the value may be relied on as an engineering fact."""
        return self.status in _FIRM_STATUSES

    @property
    def is_provisional(self) -> bool:
        """True when the value is an assumption that still needs confirmation."""
        return not self.is_firm

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "name": self.name,
            "value": self.value,
            "status": self.status.value,
            "unit": self.unit,
            "source": self.source,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngineeringParameter:
        """Restore a parameter from its dictionary form."""
        return cls(
            name=data["name"],
            value=data.get("value"),
            status=ParamStatus(data.get("status", "unknown")),
            unit=data.get("unit", "mm"),
            source=data.get("source", ""),
            note=data.get("note", ""),
        )


@dataclass
class ParameterLedger:
    """The facts-and-assumptions book for one design session.

    The ledger is the antidote to silent hallucination: before an agent uses
    a value it can ask the ledger whether that value is a fact, and every
    report keeps estimated and unknown values visible until they are resolved.

    Example:
        >>> ledger = ParameterLedger()
        >>> ledger.define(EngineeringParameter("input_speed", 300, ParamStatus.MEASURED, unit="rpm"))
        >>> ledger.define(EngineeringParameter("cam_diameter", 35, ParamStatus.ESTIMATED))
        >>> ledger.assumption_count
        1
    """

    parameters: dict[str, EngineeringParameter] = field(default_factory=dict)

    def define(self, parameter: EngineeringParameter) -> EngineeringParameter:
        """Add or replace a parameter; returns the parameter."""
        self.parameters[parameter.name] = parameter
        return parameter

    def set(
        self,
        name: str,
        value: float | str | None,
        status: ParamStatus,
        source: str = "",
    ) -> EngineeringParameter:
        """Set (or update) a parameter by name; creates it if missing."""
        if name in self.parameters:
            existing = self.parameters[name]
            existing.value = value
            existing.status = status
            if source:
                existing.source = source
            return existing
        return self.define(EngineeringParameter(name, value, status, source=source))

    def get(self, name: str) -> EngineeringParameter | None:
        """Look up a parameter by name."""
        return self.parameters.get(name)

    def value(self, name: str) -> float | str | None:
        """Current value of a parameter, or None."""
        parameter = self.parameters.get(name)
        return parameter.value if parameter else None

    @property
    def firm(self) -> list[EngineeringParameter]:
        """Parameters usable as engineering facts."""
        return [
            parameter for parameter in self.parameters.values() if parameter.is_firm
        ]

    @property
    def provisional(self) -> list[EngineeringParameter]:
        """Parameters that are assumptions (estimated/unknown/needs_data)."""
        return [
            parameter
            for parameter in self.parameters.values()
            if parameter.is_provisional
        ]

    @property
    def assumption_count(self) -> int:
        """How many values in the design are still assumptions."""
        return len(self.provisional)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "parameters": [
                parameter.to_dict() for parameter in self.parameters.values()
            ],
            "assumption_count": self.assumption_count,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Render the ledger as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render the ledger as a markdown table, assumptions flagged last."""
        lines = [
            "| parameter | value | unit | status | source |",
            "|---|---|---|---|---|",
        ]
        for parameter in self.parameters.values():
            flag = "" if parameter.is_firm else " (!)"
            lines.append(
                f"| {parameter.name} | {parameter.value} | {parameter.unit} "
                f"| {parameter.status.value}{flag} | {parameter.source or parameter.note} |"
            )
        if self.assumption_count:
            lines.append(
                f"\n{self.assumption_count} parameter(s) marked (!) are assumptions - "
                "confirm them before treating the design as final"
            )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()
