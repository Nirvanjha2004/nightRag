"""
Simple AST-based code chunker using tree-sitter.
V1: Python only. Chunks by top-level function_definition and class_definition.
No nested-function handling yet, no docstring/import extraction yet.
We'll iterate after Phase 1 verification.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path
import tree_sitter_python as tspython
from tree_sitter import Language, Parser


@dataclass
class Chunk:
    id: str
    text: str

    file_path: str

    node_type: str      # class_definition, function_definition, method_definition
    name: str

    start_line: int
    end_line: int

    @property
    def metadata(self) -> dict:
        return {
            "text": self.text,
            "file_path": self.file_path,
            "node_type": self.node_type,
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }

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
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{node.start_point[0]}")),
                        text=text,
                        file_path=file_path,
                        node_type=node.type,
                        name=name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                    )
                )

        return chunks

