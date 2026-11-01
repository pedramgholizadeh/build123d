"""Tests for engineering parameters with epistemic status."""

import json

from build123d.agentic import EngineeringParameter, ParamStatus, ParameterLedger


class TestEngineeringParameter:
    def test_firm_statuses(self):
        measured = EngineeringParameter(
            "shaft_diameter", 12.0, ParamStatus.MEASURED, source="caliper"
        )
        specified = EngineeringParameter("stroke", 40.0, ParamStatus.SPECIFIED)
        calculated = EngineeringParameter("ratio", 2.5, ParamStatus.CALCULATED)
        assert measured.is_firm and specified.is_firm and calculated.is_firm
        assert not measured.is_provisional

    def test_provisional_statuses(self):
        estimated = EngineeringParameter("cam_diameter", 35.0, ParamStatus.ESTIMATED)
        unknown = EngineeringParameter("output_force", None, ParamStatus.UNKNOWN)
        needs_data = EngineeringParameter("material", None, ParamStatus.NEEDS_DATA)
        assert (
            estimated.is_provisional
            and unknown.is_provisional
            and needs_data.is_provisional
        )
        assert not estimated.is_firm

    def test_dict_roundtrip(self):
        parameter = EngineeringParameter(
            "shaft_diameter", 12.0, ParamStatus.MEASURED, source="caliper", note="H7"
        )
        restored = EngineeringParameter.from_dict(
            json.loads(json.dumps(parameter.to_dict()))
        )
        assert restored == parameter


class TestParameterLedger:
    def test_define_and_set(self):
        ledger = ParameterLedger()
        ledger.define(
            EngineeringParameter("input_speed", 300, ParamStatus.MEASURED, unit="rpm")
        )
        ledger.set("cam_diameter", 35, ParamStatus.ESTIMATED)
        ledger.set("input_speed", 350, ParamStatus.MEASURED, source="catalog")
        assert ledger.value("input_speed") == 350
        assert ledger.value("cam_diameter") == 35
        assert ledger.get("missing") is None
        assert ledger.value("missing") is None

    def test_firm_vs_provisional_partition(self):
        ledger = ParameterLedger()
        ledger.define(EngineeringParameter("stroke", 40.0, ParamStatus.SPECIFIED))
        ledger.define(EngineeringParameter("cam_diameter", 35.0, ParamStatus.ESTIMATED))
        ledger.define(EngineeringParameter("clearance", None, ParamStatus.NEEDS_DATA))
        assert [p.name for p in ledger.firm] == ["stroke"]
        assert {p.name for p in ledger.provisional} == {"cam_diameter", "clearance"}
        assert ledger.assumption_count == 2

    def test_markdown_flags_assumptions(self):
        ledger = ParameterLedger()
        ledger.define(
            EngineeringParameter(
                "stroke", 40.0, ParamStatus.SPECIFIED, source="requirement"
            )
        )
        ledger.define(EngineeringParameter("cam_diameter", 35.0, ParamStatus.ESTIMATED))
        text = ledger.to_markdown()
        assert "| stroke | 40.0 | mm | specified | requirement |" in text
        assert "cam_diameter" in text
        assert "(!)" in text
        assert "assumptions" in text
        assert str(ledger) == text

    def test_to_dict_and_json(self):
        ledger = ParameterLedger()
        ledger.define(EngineeringParameter("stroke", 40.0, ParamStatus.SPECIFIED))
        data = ledger.to_dict()
        assert data["assumption_count"] == 0
        assert len(data["parameters"]) == 1
        assert "specified" in ledger.to_json()
