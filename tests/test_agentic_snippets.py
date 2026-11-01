"""Tests for parametric part snippets and composition."""

import textwrap

import pytest

from build123d import Box, Compound, Cylinder, Part, Pos
from build123d.agentic import SnippetRegistry, compose, snippet


@snippet(
    "test_plate",
    params={"width": {"description": "plate width", "minimum": 5.0, "maximum": 100.0}},
)
def make_plate(width: float = 20.0, thickness: float = 3.0) -> Part:
    """A simple rectangular plate."""
    return Box(width, width, thickness)


@snippet("test_post")
def make_post(height: float = 10.0) -> Part:
    """A square post standing on the XY plane."""
    return Pos(0, 0, height / 2) * Box(4, 4, height)


@snippet("test_bushing")
def make_bushing(radius: float = 5.0) -> Part:
    return Cylinder(radius, 8)


class TestSnippetDecorator:
    def test_metadata_extracted(self):
        meta = make_plate.b123d_snippet
        assert meta.name == "test_plate"
        assert meta.doc == "A simple rectangular plate."
        assert set(meta.params) == {"width", "thickness"}
        assert meta.params["width"].default == 20.0
        assert meta.params["width"].minimum == 5.0
        assert meta.params["width"].maximum == 100.0
        assert meta.params["width"].description == "plate width"
        assert meta.params["thickness"].minimum is None

    def test_annotation_recorded(self):
        meta = make_bushing.b123d_snippet
        assert "float" in meta.params["radius"].annotation


class TestRegistry:
    def test_register_and_get(self):
        registry = SnippetRegistry()
        registry.register(make_plate)
        assert registry.names == ["test_plate"]
        assert registry.get("test_plate") is make_plate
        described = registry.describe("test_plate")
        assert described["version"] == "0.1.0"
        assert described["params"][0]["name"]

    def test_register_undecorated_rejected(self):
        registry = SnippetRegistry()

        def plain(width: float = 1.0):
            return Box(width, width, width)

        with pytest.raises(ValueError):
            registry.register(plain)

    def test_unknown_snippet(self):
        registry = SnippetRegistry()
        with pytest.raises(KeyError):
            registry.get("missing")

    def test_instantiate_defaults_and_overrides(self):
        registry = SnippetRegistry()
        registry.register(make_plate)
        shape, applied = registry.instantiate("test_plate")
        assert applied == {"width": 20.0, "thickness": 3.0}
        assert isinstance(shape, Part)
        shape_big, applied_big = registry.instantiate("test_plate", width=40.0)
        assert applied_big["width"] == 40.0
        assert shape_big.volume > shape.volume

    def test_instantiate_bounds(self):
        registry = SnippetRegistry()
        registry.register(make_plate)
        with pytest.raises(ValueError, match="below minimum"):
            registry.instantiate("test_plate", width=1.0)
        with pytest.raises(ValueError, match="above maximum"):
            registry.instantiate("test_plate", width=500.0)

    def test_instantiate_unknown_param(self):
        registry = SnippetRegistry()
        registry.register(make_plate)
        with pytest.raises(ValueError, match="no parameter"):
            registry.instantiate("test_plate", diameter=10.0)

    def test_instantiate_type_error(self):
        registry = SnippetRegistry()

        @snippet("bad_return")
        def bad_return() -> float:
            return 1.0

        registry.register(bad_return)
        with pytest.raises(TypeError, match="must return"):
            registry.instantiate("bad_return")

    def test_load_from_file(self, tmp_path):
        snippet_file = tmp_path / "library.py"
        snippet_file.write_text(textwrap.dedent("""
                from build123d import Box
                from build123d.agentic import snippet

                @snippet("lib_block")
                def lib_block(size: float = 10.0):
                    return Box(size, size, size)
                """))
        registry = SnippetRegistry()
        registered = registry.load(snippet_file)
        assert registered == ["lib_block"]
        shape, applied = registry.instantiate("lib_block", size=15.0)
        assert applied["size"] == 15.0

    def test_catalog_markdown(self):
        registry = SnippetRegistry()
        registry.register(make_plate)
        registry.register(make_post)
        catalog = registry.to_markdown()
        assert "## test_plate v0.1.0" in catalog
        assert "| width | 20.0 | plate width |" in catalog
        assert "## test_post" in catalog


class TestCompose:
    def test_compose_manifest_and_labels(self):
        registry = SnippetRegistry()
        registry.register(make_plate)
        registry.register(make_post)
        composition = compose(
            [("test_plate", {"width": 30.0}), "test_post"],
            registry=registry,
            label="fixture",
        )
        assert isinstance(composition.result, Compound)
        assert composition.result.label == "fixture"
        assert len(composition.result.children) == 2
        assert composition.entries[0] == {
            "label": "test_plate_0",
            "snippet": "test_plate",
            "version": "0.1.0",
            "params": {"width": 30.0, "thickness": 3.0},
        }
        assert composition.entries[1]["snippet"] == "test_post"
        assert (
            "test_plate_0: test_plate v0.1.0 (width=30.0, thickness=3.0)"
            in composition.to_markdown()
        )

    def test_compose_default_registry(self):
        composition = compose(["test_post"], label="single")
        assert composition.result.label == "single"
        assert composition.entries[0]["snippet"] == "test_post"
