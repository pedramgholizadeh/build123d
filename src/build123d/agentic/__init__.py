"""
build123d.agentic - the AI-agentic CAD layer

build123d models are code, so agents can write them - but code alone gives
an agent no space, no consequences and no memory of what depends on what.
This package adds the missing layers that turn a code-writing agent into a
mechanical design agent. The recommended agent loop:

1. context: SpatialContext of the current model
2. plan: parameters in a ParameterLedger / FeatureGraph
3. build: snippets or a ParametricModel
4. verify: check_interference + FeatureGraph.impact/validate
5. report: markdown context, assumption list and impact analysis
"""

from build123d.agentic.parameters import (
    EngineeringParameter,
    ParamStatus,
    ParameterLedger,
)
from build123d.agentic.interference import (
    InterferencePair,
    InterferenceReport,
    check_interference,
)
from build123d.agentic.spatial_context import (
    SpatialContext,
    shape_facts,
    spatial_context,
)

__all__ = [
    # spatial context
    "SpatialContext",
    "shape_facts",
    "spatial_context",
    # interference
    "InterferencePair",
    "InterferenceReport",
    "check_interference",
    # parameters
    "EngineeringParameter",
    "ParamStatus",
    "ParameterLedger",
]
