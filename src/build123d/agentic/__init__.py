"""
build123d.agentic - the AI-agentic CAD layer

build123d models are code, so agents can write them - but code alone gives
an agent no space, no consequences and no memory of what depends on what.
This package adds the missing layers that turn a code-writing agent into a
mechanical design agent:

- build123d.agentic.spatial_context: measured spatial context
  (coordinates, bounding boxes, analytic surface equations) for prompts -
  geometry as context, never guessed.
- build123d.agentic.interference: pairwise interference / contact /
  clearance detection - physics in the loop.
- build123d.agentic.parameters: engineering parameters with epistemic
  status (measured / specified / calculated / estimated) so assumptions
  cannot pose as facts.
- build123d.agentic.feature_graph: the spatial context graph - features as
  nodes, adjacency/joints/constraints/tolerances as edges - with
  change-impact analysis.
- build123d.agentic.snippets: parametric part snippets, a registry (the
  parts-library connection point) and composition with manifests.
- build123d.agentic.ui_bridge: the rebuild-and-validate protocol that
  drag-and-drop UIs and agents both drive.
- build123d.agentic.rag: static, retrieval-ready chunking of CAD code for
  RAG pipelines.

The recommended agent loop:

1. context: SpatialContext of the current model
2. plan: parameters in a ParameterLedger / FeatureGraph
3. build: snippets or a ParametricModel
4. verify: check_interference + FeatureGraph.impact/validate
5. report: markdown context, assumption list and impact analysis
"""

from build123d.agentic.feature_graph import (
    FeatureGraph,
    FeatureNode,
    ImpactResult,
    Issue,
    Relation,
    RelationType,
    Tolerance,
)
from build123d.agentic.interference import (
    InterferencePair,
    InterferenceReport,
    check_interference,
)
from build123d.agentic.parameters import (
    EngineeringParameter,
    ParamStatus,
    ParameterLedger,
)
from build123d.agentic.rag import (
    CodeChunk,
    chunk_directory,
    chunk_file,
    read_jsonl,
    write_jsonl,
)
from build123d.agentic.snippets import (
    Composition,
    ParamMeta,
    SnippetMeta,
    SnippetRegistry,
    compose,
    snippet,
)
from build123d.agentic.spatial_context import (
    SpatialContext,
    shape_facts,
    spatial_context,
)
from build123d.agentic.ui_bridge import BuildResult, Parameter, ParametricModel

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
    # feature graph
    "FeatureGraph",
    "FeatureNode",
    "ImpactResult",
    "Issue",
    "Relation",
    "RelationType",
    "Tolerance",
    # snippets
    "Composition",
    "ParamMeta",
    "SnippetMeta",
    "SnippetRegistry",
    "compose",
    "snippet",
    # ui bridge
    "BuildResult",
    "Parameter",
    "ParametricModel",
    # rag
    "CodeChunk",
    "chunk_directory",
    "chunk_file",
    "read_jsonl",
    "write_jsonl",
]
