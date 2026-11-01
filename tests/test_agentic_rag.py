"""Tests for RAG chunking of CAD code."""

import textwrap

from build123d.agentic import chunk_directory, chunk_file, read_jsonl, write_jsonl

SAMPLE = '''
"""A small parts library for the pump project."""

from build123d import Box, Cylinder
from build123d.agentic import snippet

BORE_DEFAULT = 10.0
MATERIAL = "aluminum"


@snippet("bearing")
def bearing(r: float = 10.0, h: float = 5.0) -> "Part":
    """A simple bearing bushing."""
    return Cylinder(r, h)


class BearingKeeper:
    """Keeps bearings sorted."""
'''


class TestChunkFile:
    def test_module_chunk(self, tmp_path):
        file = tmp_path / "library.py"
        file.write_text(SAMPLE)
        chunks = chunk_file(file)
        module = chunks[0]
        assert module.kind == "module"
        assert module.doc and "parts library" in module.doc
        assert module.imports == ["build123d"]
        assert "build123d" in module.tags

    def test_function_chunk_with_params(self, tmp_path):
        file = tmp_path / "library.py"
        file.write_text(SAMPLE)
        chunks = chunk_file(file)
        bearing = next(chunk for chunk in chunks if chunk.symbol == "bearing")
        assert bearing.kind == "function"
        assert bearing.doc == "A simple bearing bushing."
        params = {param["name"]: param for param in bearing.params}
        assert params["r"]["default"] == 10.0
        assert params["r"]["annotation"] == "float"
        assert params["h"]["default"] == 5.0
        assert "part-snippet" in bearing.tags
        assert "Cylinder" in bearing.source
        assert bearing.line_start < bearing.line_end
        assert bearing.id.endswith("::bearing")

    def test_function_without_defaults(self, tmp_path):
        file = tmp_path / "plain.py"
        file.write_text(textwrap.dedent("""
                def align(a, b=2):
                    return a + b
                """))
        (chunk,) = [c for c in chunk_file(file) if c.kind == "function"]
        params = {param["name"]: param for param in chunk.params}
        assert params["a"]["default"] is None
        assert params["b"]["default"] == 2

    def test_class_chunk(self, tmp_path):
        file = tmp_path / "library.py"
        file.write_text(SAMPLE)
        chunks = chunk_file(file)
        keeper = next(chunk for chunk in chunks if chunk.symbol == "BearingKeeper")
        assert keeper.kind == "class"
        assert "sorted" in keeper.doc

    def test_embedding_text(self, tmp_path):
        file = tmp_path / "library.py"
        file.write_text(SAMPLE)
        chunks = chunk_file(file)
        bearing = next(chunk for chunk in chunks if chunk.symbol == "bearing")
        text = bearing.embedding_text()
        assert "library.py::bearing (function)" in text
        assert "r=10.0:float" in text
        assert "A simple bearing bushing." in text

    def test_constants_in_module_chunk(self, tmp_path):
        file = tmp_path / "library.py"
        file.write_text(SAMPLE)
        module = chunk_file(file)[0]
        assert "constants" in module.tags
        assert "BORE_DEFAULT = 10.0" in module.source


class TestChunkDirectoryAndJsonl:
    def test_directory_and_jsonl_roundtrip(self, tmp_path):
        (tmp_path / "parts").mkdir()
        (tmp_path / "parts" / "library.py").write_text(SAMPLE)
        (tmp_path / "parts" / "broken.py").write_text("def broken(:\n")
        chunks = chunk_directory(tmp_path / "parts")
        assert any(chunk.symbol == "bearing" for chunk in chunks)
        assert all(chunk.file for chunk in chunks)

        target = tmp_path / "index.jsonl"
        write_jsonl(chunks, target)
        records = read_jsonl(target)
        assert len(records) == len(chunks)
        assert records[0]["kind"] == "module"
        assert any(record["symbol"] == "bearing" for record in records)
