"""
Parametric Part Snippets

Standard engineering models mix code, formulas and numbers. A multi-part
model is easiest to keep sane when each part is a small, parameterized,
reusable unit - a snippet - that a bigger model embeds like a code snippet,
with parameter overrides recorded so agents (and humans) can trace exactly
what was built with what values. The registry doubles as the connection
point for parts libraries.

name: snippets.py
by:   build123d agentic layer
date: November 1, 2026

desc:
    @snippet decorator, SnippetRegistry (register/load/instantiate/catalog)
    and compose(): build multi-part models from parameterized parts with a
    recorded manifest.

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

import importlib.util
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from build123d import Compound, Shape

__all__ = [
    "Composition",
    "ParamMeta",
    "SnippetMeta",
    "SnippetRegistry",
    "compose",
    "snippet",
]


@dataclass
class ParamMeta:
    """Metadata for one snippet parameter.

    Attributes:
        name: parameter name.
        default: the function's default value.
        annotation: type annotation as written, if any.
        description: what the parameter controls.
        minimum: smallest allowed value (numeric parameters).
        maximum: largest allowed value (numeric parameters).
    """

    name: str
    default: Any = None
    annotation: str = ""
    description: str = ""
    minimum: float | None = None
    maximum: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "name": self.name,
            "default": self.default,
            "annotation": self.annotation,
            "description": self.description,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass
class SnippetMeta:
    """Metadata attached to a @snippet-decorated function.

    Attributes:
        name: registry name of the snippet.
        version: snippet version string.
        params: parameter metadata by name.
        doc: the function's docstring.
        source_file: file the snippet was defined in.
        tags: free-form tags for catalog filtering and RAG indexing.
    """

    name: str
    version: str = "0.1.0"
    params: dict[str, ParamMeta] = field(default_factory=dict)
    doc: str = ""
    source_file: str = ""
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "name": self.name,
            "version": self.version,
            "params": [param.to_dict() for param in self.params.values()],
            "doc": self.doc,
            "source_file": self.source_file,
            "tags": list(self.tags),
        }


def snippet(
    name: str | None = None,
    *,
    version: str = "0.1.0",
    params: dict[str, dict[str, Any]] | None = None,
    tags: Sequence[str] = (),
) -> Callable:
    """Mark a function as a reusable parametric part snippet.

    The function must return a build123d Shape. Its signature becomes the
    parameter schema; the optional ``params`` mapping adds descriptions and
    numeric bounds per parameter::

        @snippet("iso_flange", params={"dn": {"description": "nominal bore"}})
        def iso_flange(dn: float = 50.0, bolts: int = 4) -> Part: ...

    Args:
        name: registry name (defaults to the function name).
        version: snippet version.
        params: per-parameter metadata: {"description": str,
            "minimum": float, "maximum": float}.
        tags: catalog/RAG tags.

    Returns:
        A decorator that attaches :class:`SnippetMeta` to the function.
    """

    def decorator(func: Callable) -> Callable:
        """Attach snippet metadata extracted from the function signature."""
        extra = params or {}
        schema: dict[str, ParamMeta] = {}
        signature = inspect.signature(func)
        for param_name, param in signature.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            spec = extra.get(param_name, {})
            default = param.default if param.default is not param.empty else None
            schema[param_name] = ParamMeta(
                name=param_name,
                default=default,
                annotation=(
                    "" if param.annotation is param.empty else str(param.annotation)
                ),
                description=spec.get("description", ""),
                minimum=spec.get("minimum"),
                maximum=spec.get("maximum"),
            )
        func.b123d_snippet = SnippetMeta(  # type: ignore[attr-defined]
            name=name or func.__name__,
            version=version,
            params=schema,
            doc=inspect.getdoc(func) or "",
            source_file=inspect.getsourcefile(func) or "",
            tags=tuple(tags),
        )
        DEFAULT_REGISTRY.register(func)
        return func

    return decorator


@dataclass
class Composition:
    """The result of composing snippets into a multi-part model.

    Attributes:
        result: the assembled Compound.
        entries: one record per part: {"label", "snippet", "version",
            "params"} - the manifest of what was built with what.
    """

    result: Compound
    entries: list[dict[str, Any]] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the composition manifest for agent context."""
        lines = [f"# Composition ({len(self.entries)} parts)"]
        for entry in self.entries:
            rendered = ", ".join(
                f"{key}={value}" for key, value in entry["params"].items()
            )
            lines.append(
                f"- {entry['label']}: {entry['snippet']} v{entry['version']}"
                + (f" ({rendered})" if rendered else "")
            )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()


class SnippetRegistry:
    """A named collection of parametric part snippets.

    The registry is the "parts library" connection point: load a directory
    of snippet files once, then instantiate parts by name with parameter
    overrides - in scripts, agent tools or a UI.
    """

    def __init__(self) -> None:
        self._snippets: dict[str, Callable] = {}

    # ---- Registration ----

    def register(self, func: Callable) -> Callable:
        """Register a @snippet-decorated function; returns the function."""
        meta = getattr(func, "b123d_snippet", None)
        if meta is None:
            raise ValueError(
                f"{getattr(func, '__name__', func)} is not decorated with @snippet"
            )
        self._snippets[meta.name] = func
        return func

    def load(self, path: str | Path) -> list[str]:
        """Import a snippet file (or every *.py in a directory) and register
        all decorated functions found.

        Args:
            path: a .py file or a directory of them.

        Returns:
            The names that were registered.
        """
        path = Path(path)
        files = [path] if path.is_file() else sorted(path.glob("*.py"))
        registered: list[str] = []
        for file in files:
            module_name = f"b3d_snippets_{file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file)
            if spec is None or spec.loader is None:  # pragma: no cover
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            for obj in vars(module).values():
                if callable(obj) and hasattr(obj, "b123d_snippet"):
                    self.register(obj)
                    registered.append(obj.b123d_snippet.name)  # type: ignore[attr-defined]
        return registered

    # ---- Access ----

    def get(self, name: str) -> Callable:
        """Look up a snippet by name.

        Raises:
            KeyError: if the name is not registered.
        """
        if name not in self._snippets:
            raise KeyError(
                f"unknown snippet '{name}'; registered: {sorted(self._snippets)}"
            )
        return self._snippets[name]

    @property
    def names(self) -> list[str]:
        """All registered snippet names."""
        return sorted(self._snippets)

    def describe(self, name: str) -> dict[str, Any]:
        """Full metadata of one snippet as a dict."""
        return self.get(name).b123d_snippet.to_dict()  # type: ignore[attr-defined]

    def to_markdown(self) -> str:
        """Render the whole catalog (RAG- and human-friendly)."""
        lines = [f"# Snippet Catalog ({len(self._snippets)} snippets)"]
        for name in self.names:
            meta: SnippetMeta = self.get(name).b123d_snippet  # type: ignore[attr-defined]
            lines.append(f"\n## {meta.name} v{meta.version}")
            if meta.doc:
                lines.append(meta.doc.strip())
            if meta.params:
                lines.append("| parameter | default | description |")
                lines.append("|---|---|---|")
                for param in meta.params.values():
                    lines.append(
                        f"| {param.name} | {param.default} | {param.description} |"
                    )
        return "\n".join(lines)

    # ---- Instantiation ----

    def instantiate(self, name: str, **overrides: Any) -> tuple[Shape, dict[str, Any]]:
        """Build one snippet with parameter overrides.

        Args:
            name: registered snippet name.
            **overrides: parameter values; must exist on the snippet and
                respect its minimum/maximum bounds.

        Returns:
            (shape, applied_params) where applied_params are the actual
            values used (defaults merged with overrides).

        Raises:
            KeyError: unknown snippet name.
            ValueError: unknown parameter or value outside bounds.
        """
        func = self.get(name)
        meta: SnippetMeta = func.b123d_snippet  # type: ignore[attr-defined]
        applied: dict[str, Any] = {
            param: spec.default for param, spec in meta.params.items()
        }
        for param, value in overrides.items():
            if param not in meta.params:
                raise ValueError(f"snippet '{name}' has no parameter '{param}'")
            spec = meta.params[param]
            if isinstance(value, (int, float)):
                if spec.minimum is not None and value < spec.minimum:
                    raise ValueError(
                        f"{name}.{param}={value} below minimum {spec.minimum}"
                    )
                if spec.maximum is not None and value > spec.maximum:
                    raise ValueError(
                        f"{name}.{param}={value} above maximum {spec.maximum}"
                    )
            applied[param] = value
        shape = func(**applied)
        if not isinstance(shape, Shape):
            raise TypeError(
                f"snippet '{name}' must return a build123d Shape, got {type(shape).__name__}"
            )
        return shape, applied


#: Registry the @snippet decorator registers into by default, and the one
#: compose() uses when no explicit registry is passed.
DEFAULT_REGISTRY = SnippetRegistry()


def compose(
    specs: Sequence[str | tuple[str, dict[str, Any]]],
    *,
    registry: SnippetRegistry | None = None,
    label: str = "assembly",
) -> Composition:
    """Compose snippets into one multi-part model.

    Each part is instantiated (with overrides) and embedded into a Compound,
    like a snippet pasted into code - and the manifest records exactly which
    snippet and parameters produced each part.

    Args:
        specs: snippet names, or (name, overrides) tuples.
        registry: registry to use (defaults to a fresh one; pass a loaded
            registry for real part libraries).
        label: label of the resulting Compound.

    Returns:
        A Composition with the assembled Compound and its manifest.

    Example:
        >>> from build123d.agentic import SnippetRegistry, compose
        >>> registry = SnippetRegistry()
        >>> registry.load("my_parts/")
        >>> model = compose(
        ...     [("housing", {"bore": 30.0}), "cover"],
        ...     registry=registry,
        ...     label="pump",
        ... )
        >>> model.result.label
        'pump'
    """
    registry = registry or DEFAULT_REGISTRY
    children: list[Shape] = []
    entries: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        name, overrides = spec if isinstance(spec, tuple) else (spec, {})
        shape, applied = registry.instantiate(name, **overrides)
        if not shape.label:
            shape.label = f"{name}_{index}"
        children.append(shape)
        entries.append(
            {
                "label": shape.label,
                "snippet": name,
                "version": registry.describe(name)["version"],
                "params": applied,
            }
        )
    result = Compound(children=children, label=label)
    return Composition(result=result, entries=entries)
