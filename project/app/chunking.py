"""
Simple AST-based code chunker using tree-sitter.
V1: Python only. Chunks by top-level function_definition and class_definition.
No nested-function handling yet, no docstring/import extraction yet.
We'll iterate after Phase 1 verification.
"""

from dataclasses import dataclass
from pathlib import Path
import tree_sitter_python as tspython
from tree_sitter import Language, Parser


@dataclass
class Chunk:
    text: str
    file_path: str
    node_type: str          # "function_definition" or "class_definition"
    name: str                # function/class name
    start_line: int          # 1-indexed
    end_line: int             # 1-indexed


class PythonChunker:
    def __init__(self):
        py_language = Language(tspython.language())
        self.parser = Parser(py_language)

    def _get_node_name(self, node, source_bytes: bytes) -> str:
        """Find the identifier child (function/class name)."""
        for child in node.children:
            if child.type == "identifier":
                return source_bytes[child.start_byte:child.end_byte].decode("utf-8")
        return "<anonymous>"

    def chunk_file(self, file_path: str) -> list[Chunk]:
        source_bytes = Path(file_path).read_bytes()
        tree = self.parser.parse(source_bytes)
        root = tree.root_node

        chunks: list[Chunk] = []

        # Only look at top-level nodes for now (v1 = simple, no recursion into nested defs)
        for node in root.children:
            if node.type in ("function_definition", "class_definition"):
                text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                name = self._get_node_name(node, source_bytes)
                chunks.append(
                    Chunk(
                        text=text,
                        file_path=file_path,
                        node_type=node.type,
                        name=name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                    )
                )

        return chunks


if __name__ == "__main__":
    # Quick manual test — point this at any .py file in your target repo
    import sys
    import random

    if len(sys.argv) < 2:
        print("Usage: python chunker.py <path_to_python_file>")
        sys.exit(1)

    chunker = PythonChunker()
    chunks = chunker.chunk_file(sys.argv[1])

    print(f"Found {len(chunks)} chunks in {sys.argv[1]}\n")

    # Print up to 15 random chunks for manual verification (Phase 1 gate)
    sample = random.sample(chunks, min(15, len(chunks)))
    for c in sample:
        print("=" * 60)
        print(f"[{c.node_type}] {c.name}  (lines {c.start_line}-{c.end_line})")
        print("-" * 60)
        print(c.text[:300] + ("..." if len(c.text) > 300 else ""))
        print()