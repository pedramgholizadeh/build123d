"""
RAG Indexing for CAD Code

Retrieval-augmented generation over a CAD codebase needs chunks that mean
something to an engineer: a parametric part function with its parameters
and docstring, not a random 500-token window. This module parses Python
files statically (no code execution), extracts functions, classes, snippet
metadata and module constants, and writes embedding-ready JSONL chunks.

name: rag.py
by:   build123d agentic layer
date: November 1, 2026

desc:
    CodeChunk / chunk_file / chunk_directory / write_jsonl: static AST
    chunking of build123d model code into retrieval-ready units with
    parameters, docstrings, imports and @snippet metadata.

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

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["CodeChunk", "chunk_directory", "chunk_file", "write_jsonl"]


@dataclass
class CodeChunk:
    """One retrieval unit of CAD code.

    Attributes:
        id: "file::symbol" identifier.
        file: path of the source file.
        symbol: function/class/module name.
        kind: "function", "class" or "module".
        doc: docstring, if any.
        params: [{"name", "default", "annotation"}] for functions.
        source: the extracted source text.
        line_start: 1-based start line.
        line_end: 1-based end line (inclusive).
        imports: modules imported by the file.
        tags: e.g. "build123d", "part-snippet".
    """

    id: str
    file: str
    symbol: str
    kind: str
    doc: str = ""
    params: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""
    line_start: int = 0
    line_end: int = 0
    imports: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "id": self.id,
            "file": self.file,
            "symbol": self.symbol,
            "kind": self.kind,
            "doc": self.doc,
            "params": self.params,
            "source": self.source,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "imports": self.imports,
            "tags": self.tags,
        }

    def embedding_text(self) -> str:
        """Compact text for embedding models: identity, doc, schema, code."""
        lines = [f"{self.file}::{self.symbol} ({self.kind})"]
        if self.doc:
            lines.append(self.doc.strip())
        if self.params:
            rendered = ", ".join(
                f"{param['name']}={param['default']}"
                + (f":{param['annotation']}" if param["annotation"] else "")
                for param in self.params
            )
            lines.append(f"parameters: {rendered}")
        if self.source:
            lines.append(self.source)
        return "\n".join(lines)


def _literal(node: ast.AST | None) -> Any:
    """Best-effort literal value of an AST node."""
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return ast.unparse(node) if hasattr(ast, "unparse") else None


def _imports_of(tree: ast.Module) -> list[str]:
    """Top-level module names imported by a parsed file."""
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module.split(".")[0])
    return sorted(set(modules))


def _is_snippet(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when the function is decorated with something named like @snippet."""
    for decorator in node.decorator_list:
        name = (
            decorator.func.id
            if isinstance(decorator, ast.Call) and hasattr(decorator.func, "id")
            else (decorator.id if isinstance(decorator, ast.Name) else "")
        )
        if "snippet" in name.lower():
            return True
    return False


def chunk_file(path: str | Path) -> list[CodeChunk]:
    """Parse one Python file into retrieval chunks (statically, no execution).

    Args:
        path: the file to parse.

    Returns:
        One chunk per top-level function and class, plus a "module" chunk
        carrying the docstring, imports and top-level constants.

    Raises:
        FileNotFoundError: if the file does not exist.
        SyntaxError: if the file does not parse.
    """
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    file_imports = _imports_of(tree)
    base_tags = ["build123d"] if "build123d" in file_imports else []
    relative = str(path)

    chunks: list[CodeChunk] = []
    module_doc = ast.get_docstring(tree) or ""
    constants: dict[str, Any] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            value = _literal(node.value)
            if value is not None:
                constants[node.targets[0].id] = value

    chunks.append(
        CodeChunk(
            id=f"{relative}::<module>",
            file=relative,
            symbol="<module>",
            kind="module",
            doc=module_doc,
            source=source,
            line_start=1,
            line_end=len(source.splitlines()) or 1,
            imports=file_imports,
            tags=base_tags + (["constants"] if constants else []),
        )
    )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaulted = len(node.args.defaults)
            positional = [*node.args.posonlyargs, *node.args.args]
            params = []
            for index, arg in enumerate(positional):
                default_index = index - (len(positional) - defaulted)
                params.append(
                    {
                        "name": arg.arg,
                        "default": (
                            _literal(node.args.defaults[default_index])
                            if default_index >= 0
                            else None
                        ),
                        "annotation": (
                            ast.unparse(arg.annotation) if arg.annotation else ""
                        ),
                    }
                )
            if node.args.kwonlyargs:
                for index, arg in enumerate(node.args.kwonlyargs):
                    params.append(
                        {
                            "name": arg.arg,
                            "default": _literal(node.args.kw_defaults[index]),
                            "annotation": (
                                ast.unparse(arg.annotation) if arg.annotation else ""
                            ),
                        }
                    )
            tags = list(base_tags)
            if _is_snippet(node):
                tags.append("part-snippet")
            chunks.append(
                CodeChunk(
                    id=f"{relative}::{node.name}",
                    file=relative,
                    symbol=node.name,
                    kind="function",
                    doc=ast.get_docstring(node) or "",
                    params=params,
                    source=ast.get_source_segment(source, node) or "",
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    imports=file_imports,
                    tags=tags,
                )
            )
        elif isinstance(node, ast.ClassDef):
            chunks.append(
                CodeChunk(
                    id=f"{relative}::{node.name}",
                    file=relative,
                    symbol=node.name,
                    kind="class",
                    doc=ast.get_docstring(node) or "",
                    source=ast.get_source_segment(source, node) or "",
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    imports=file_imports,
                    tags=base_tags,
                )
            )
    return chunks


def chunk_directory(
    path: str | Path,
    *,
    pattern: str = "**/*.py",
) -> list[CodeChunk]:
    """Chunk every matching Python file under a directory.

    Args:
        path: root directory (a parts library, a project of models, ...).
        pattern: glob relative to the path.

    Returns:
        All chunks, files in sorted order.
    """
    path = Path(path)
    chunks: list[CodeChunk] = []
    for file in sorted(path.glob(pattern)):
        if "__pycache__" in file.parts or file.name.startswith("."):
            continue
        try:
            chunks += chunk_file(file)
        except SyntaxError:
            continue  # a file that does not parse is not retrievable content
    return chunks


def write_jsonl(chunks: list[CodeChunk], path: str | Path) -> Path:
    """Write chunks as JSONL (one JSON object per line) for embedding pipelines.

    Args:
        chunks: chunks to write.
        path: output file path.

    Returns:
        The output path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        for chunk in chunks:
            stream.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL chunk file back as dictionaries."""
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
