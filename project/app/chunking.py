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
    # v2: added decorated_definition and async_function_definition
    _DEF_TYPES = frozenset({
        "function_definition",
        "class_definition",
        "async_function_definition",
        "decorated_definition",
    })

    def __init__(self):
        py_language = Language(tspython.language())
        self.parser = Parser(py_language)

    def _name(self, node, source: bytes) -> str:
        """Return the identifier of a definition, looking through decorators if needed."""
        target = node
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in ("function_definition", "class_definition", "async_function_definition"):
                    target = child
                    break
        for child in target.children:
            if child.type == "identifier":
                return source[child.start_byte:child.end_byte].decode("utf-8")
        return "<anonymous>"

    def _inner_def(self, node):
        """If node is decorated, return the wrapped definition; else return node."""
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in ("function_definition", "class_definition", "async_function_definition"):
                    return child
        return node

    def _chunk(self, node, source: bytes, file_path: str, name: str, node_type: str) -> Chunk:
        return Chunk(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{node.start_point[0]}")),
            text=source[node.start_byte:node.end_byte].decode("utf-8"),
            file_path=file_path,
            node_type=node_type,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        )

    def chunk_file(self, file_path: str) -> list[Chunk]:
        source = Path(file_path).read_bytes()
        root = self.parser.parse(source).root_node

        chunks: list[Chunk] = []

        for node in root.children:
            if node.type not in self._DEF_TYPES:
                continue

            inner = self._inner_def(node)
            name = self._name(inner, source)

            if inner.type == "class_definition":
                body = next((c for c in inner.children if c.type == "block"), None)
                methods: list[Chunk] = []
                if body:
                    for child in body.children:
                        if child.type not in self._DEF_TYPES:
                            continue
                        m_inner = self._inner_def(child)
                        m_name = self._name(m_inner, source)
                        methods.append(self._chunk(
                            child, source, file_path,
                            name=f"{name}.{m_name}",
                            node_type="method_definition",
                        ))
                if methods:
                    # ponytail: class body is dropped when methods exist to avoid 413s on huge classes.
                    # Methods carry fully-qualified names so context isn't lost.
                    # Ceiling: class-level vars/imports inside a class with methods are invisible.
                    # Upgrade path: emit a skeleton chunk (decorators + class line + docstring)
                    # if you need class-level context back.
                    chunks.extend(methods)
                else:
                    # No methods — class is small enough to keep whole
                    chunks.append(self._chunk(
                        node, source, file_path,
                        name=name,
                        node_type="class_definition",
                    ))
            else:
                # v2: use the outer node (decorated_definition) so decorators are included in text
                chunks.append(self._chunk(
                    node, source, file_path,
                    name=name,
                    node_type=inner.type,
                ))

        return chunks