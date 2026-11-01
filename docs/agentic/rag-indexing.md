# RAG Indexing for CAD Code

> Problem it solves: agents repeat past work and cannot find project
> knowledge. The fix: chunk CAD code into units that *mean something to an
> engineer* — a parametric part function with its parameters and docstring,
> not a random 500-token window — and write embedding-ready JSONL.

## What it does

`build123d.agentic.rag` parses Python files **statically** (AST only —
never executes the code) and extracts:

- one chunk per top-level function/class: docstring, parameter schema
  (names, defaults, annotations), source, line range, imports
- one `module` chunk per file: docstring, imports, top-level constants
- tags: `build123d` (file imports build123d), `part-snippet` (function is
  decorated with `@snippet`), `constants`

## Quick start

```python
from build123d.agentic import chunk_directory, chunk_file, write_jsonl

# one file
chunks = chunk_file("pump/impeller.py")

# a whole parts library / project
chunks = chunk_directory("my_parts/", pattern="**/*.py")

# embedding-ready JSONL: one JSON object per line
write_jsonl(chunks, "index.jsonl")
```

## Chunk shape

```python
{
  "id": "pump/impeller.py::impeller",
  "file": "pump/impeller.py",
  "symbol": "impeller",
  "kind": "function",
  "doc": "A five-blade impeller ...",
  "params": [{"name": "bore", "default": 10.0, "annotation": "float"}, ...],
  "source": "def impeller(bore: float = 10.0): ...",
  "line_start": 12, "line_end": 40,
  "imports": ["build123d"],
  "tags": ["build123d", "part-snippet"],
}
```

`chunk.embedding_text()` renders the compact form for the embedding model:
identity line, docstring, parameter schema, then source.

## Plugging into a vector store

The JSONL is store-agnostic — for each record: `text = embedding_text()`,
metadata = the rest. Then retrieval for "how did we model the volute last
time?" returns the actual volute function with its parameters, and the
agent starts from working code instead of hallucinating a new one.

Recommended retrieval filters:

- `tags contains "part-snippet"` — prefer reusable parametric parts
- `kind == "function"` and parameter names matching the query
- `imports contains "build123d"` — skip non-CAD noise

## Boundaries

- Static analysis only: decorators are detected by name (anything
  `*snippet*`), defaults must be literals to be captured (otherwise
  `null`), no execution ever happens.
- Files that fail to parse are skipped by `chunk_directory` (they carry no
  reliable content) — `chunk_file` raises so callers can see the error.
- `__pycache__` and dotfiles are ignored.

See `tests/test_agentic_rag.py` for behavior examples.
