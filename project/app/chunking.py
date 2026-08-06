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
    node_type: str      # class_definition, function_definition, method_definition, class_header
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

    # ---------- text helpers ----------

    def _node_text(self, node, source: bytes, up_to=None) -> str:
        """Slice raw text from node start up to (but not including) `up_to` node, or full node."""
        end = up_to.start_byte if up_to else node.end_byte
        return source[node.start_byte:end].decode("utf-8").rstrip()

    def _sig_line(self, inner, source: bytes) -> str:
        """The 'class Console(...):' line — everything before the body block starts."""
        body = next((c for c in inner.children if c.type == "block"), None)
        end = body.start_byte if body else inner.end_byte
        return source[inner.start_byte:end].decode("utf-8").rstrip()

    def _is_docstring(self, node) -> bool:
        """True if this expression_statement is just a bare string literal."""
        return len(node.children) == 1 and node.children[0].type == "string"

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

    # ---------- chunk builders ----------

    def _chunk(self, node, source: bytes, file_path: str, name: str, node_type: str) -> Chunk:
        # id keyed on (file_path, node_type, qualified name) — NOT line number.
        # A line shifting (e.g. blank line added above) no longer changes the id;
        # only an actual rename/move does. This is what lets ingest overwrite
        # instead of duplicating on re-runs, and lets Phase 3 (BM25) share ids
        # with the vector index.
        return Chunk(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{node_type}:{name}")),
            text=source[node.start_byte:node.end_byte].decode("utf-8"),
            file_path=file_path,
            node_type=node_type,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        )

    def _chunk_from_text(self, text, file_path, name, node_type, start_line, end_line) -> Chunk:
        return Chunk(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{node_type}:{name}")),
            text=text,
            file_path=file_path,
            node_type=node_type,
            name=name,
            start_line=start_line,
            end_line=end_line,
        )

    def _skeleton_chunk(self, node, inner, body, source, file_path, name):
        """Header chunk for a class whose body was split into method chunks:
        decorators + 'class X(...):' line + docstring + class-level attrs.
        Method bodies themselves are intentionally excluded."""
        parts = [self._node_text(node, source, up_to=inner)]  # decorators, if any (empty string if none)
        parts.append(self._sig_line(inner, source))            # "class Console(...):"

        for child in body.children:
            if child.type == "expression_statement" and self._is_docstring(child):
                parts.append(self._node_text(child, source))
            elif child.type == "expression_statement":  # class-level attrs like `x: int` / `CONST = 5`
                parts.append(self._node_text(child, source))

        text = "\n".join(p for p in parts if p)
        end_line = body.children[0].start_point[0] if body.children else node.end_point[0] + 1

        return self._chunk_from_text(
            text, file_path, name=name, node_type="class_header",
            start_line=node.start_point[0] + 1,
            end_line=end_line,
        )

    # ---------- main entry point ----------

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

                        if m_inner.type == "class_definition":
                            # nested class — tagged distinctly so it isn't mistaken
                            # for a plain method. Not recursively split (rare case,
                            # revisit if a real file needs it).
                            methods.append(self._chunk(
                                child, source, file_path,
                                name=f"{name}.{m_name}",
                                node_type="nested_class_definition",
                            ))
                        else:
                            methods.append(self._chunk(
                                child, source, file_path,
                                name=f"{name}.{m_name}",
                                node_type="method_definition",
                            ))

                if methods:
                    header_chunk = self._skeleton_chunk(node, inner, body, source, file_path, name)
                    chunks.append(header_chunk)
                    chunks.extend(methods)
                else:
                    # No methods — class is small enough to keep whole
                    chunks.append(self._chunk(
                        node, source, file_path,
                        name=name,
                        node_type="class_definition",
                    ))
            else:
                # decorated_definition / function_definition / async_function_definition
                # use the outer node so decorators are included in the text
                chunks.append(self._chunk(
                    node, source, file_path,
                    name=name,
                    node_type=inner.type,
                ))

        return chunks