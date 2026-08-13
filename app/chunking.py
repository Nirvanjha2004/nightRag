"""
chunking.py — AST-aware code chunker for many languages.

Splits source files into chunks at definition boundaries (functions, classes,
methods, ...) using tree-sitter. The driving idea: chunk the way a reader
browses a file. A class with members becomes a *header* chunk (signature +
leading doc comment + class-level fields) plus one chunk per member; anything
else — free functions, small classes — is kept whole.

Language support is config-driven (see `LanguageConfig`): each language
declares the tree-sitter node types that define symbols, the shape of class
bodies, and how names are found. Grammars are loaded lazily — a language
whose package is not installed is simply not registered, so partial installs
still work. `chunk_file()` dispatches by file extension and raises
`ValueError` for unknown ones.

Supported: Python, JavaScript/JSX, TypeScript/TSX, Java, Go, Rust, C, C++,
C#, Ruby, PHP, Kotlin, Swift.
"""

import importlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Node, Parser


@dataclass
class Chunk:
    """A single retrievable unit of source code."""

    id: str
    text: str
    file_path: str
    node_type: str      # method_definition, function_definition, class_header, ...
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


@dataclass(frozen=True)
class LanguageConfig:
    """Everything the generic chunker needs to know about one language.

    All `*_types` sets hold tree-sitter node type names.

    - def_types: node types that define a symbol (function, class, method...)
    - class_types: def types whose bodies are split into header + members
      (class, struct, interface, enum, impl, trait, ...)
    - body_types: node types that contain a class-like's members
      (block, class_body, declaration_list, field_declaration_list, ...)
    - method_types: def types that are function-like. Inside a class body they
      become ``method_definition``; at top level ``function_definition``.
    - always_method_types: def types that are always methods even at top level
      (Go's receiver-based ``method_declaration``).
    - name_types: node types that can be a definition's name.
    - name_field: tree-sitter *field* name holding the name (C#'s "name").
    - name_skip_types: child subtree types to skip while searching for a name
      (Java modifiers, Go's receiver parameter_list).
    - name_in_types: child types to search *inside* for a name
      (Rust's generic type path in impl blocks).
    - name_fn: custom name lookup (C/C++ declarator chains).
    - wrapper_types: def types that wrap exactly one inner def and whose text
      should be kept (decorated_definition, export_statement,
      template_declaration, attribute_item, ...).
    - container_types: def types that may wrap *several* inner defs, each
      chunked separately (Go's grouped ``type ( ... )`` declaration).
    - scope_types: containers whose members are NOT methods and whose name
      qualifies everything inside (namespace_definition, Rust mod, Ruby
      module, C# namespace).
    - header_member_types: class-body node types kept in the header chunk
      (class-level fields, attributes, docstrings).
    - leading_types: node types that are collected as leading docs above a
      def and folded into its chunk text (comments everywhere; Rust also
      collects attribute_item so `#[derive(Debug)]` sticks with its struct).
    - declaration_types: node types that *declare* symbols via a name/value
      pair (JS/TS `lexical_declaration`/`variable_declaration` for
      `const foo = () => {}`). Only declarators whose value is a function
      (see function_value_types) are chunked — plain constants would be noise.
    - function_value_types: value node types treated as functions inside a
      declaration (arrow_function, function_expression).
    """

    name: str
    extensions: tuple[str, ...]
    language: Language
    def_types: frozenset[str]
    class_types: frozenset[str]
    body_types: frozenset[str]
    name_types: frozenset[str]
    wrapper_types: frozenset[str] = frozenset()
    container_types: frozenset[str] = frozenset()
    scope_types: frozenset[str] = frozenset()
    header_member_types: frozenset[str] = frozenset()
    method_types: frozenset[str] = frozenset()
    always_method_types: frozenset[str] = frozenset()
    leading_types: frozenset[str] = frozenset({"comment"})
    declaration_types: frozenset[str] = frozenset()
    function_value_types: frozenset[str] = frozenset({"arrow_function", "function_expression", "function"})
    name_field: str | None = None
    name_skip_types: frozenset[str] = frozenset()
    name_in_types: frozenset[str] = frozenset()
    name_fn: Callable[[Node, bytes], str | None] | None = None


def _declarator_name(node: Node, source: bytes) -> str | None:
    """C/C++: walk the ``declarator`` field chain to the innermost name.

    Handles pointers (``int *foo``), functions (``int foo(...)``), and
    qualified out-of-line methods (``void Foo::bar()`` -> ``bar``). Returns
    None when the node has no declarator chain (e.g. a class_specifier),
    letting the generic name scan take over.
    """
    target = node
    seen: set[int] = set()
    while True:
        if target.type in ("identifier", "field_identifier", "type_identifier"):
            return source[target.start_byte:target.end_byte].decode("utf-8")
        if target.type == "qualified_identifier":
            names = [c for c in target.children
                     if c.type in ("identifier", "field_identifier", "type_identifier")]
            if names:
                last = names[-1]
                return source[last.start_byte:last.end_byte].decode("utf-8")
        nxt = target.child_by_field_name("declarator")
        if nxt is None or nxt == target or id(nxt) in seen:
            return None
        seen.add(id(nxt))
        target = nxt


class CodeChunker:
    """Config-driven chunker. See `LanguageConfig` for the per-language knobs."""

    def __init__(self, config: LanguageConfig):
        self.config = config
        self.parser = Parser(config.language)
        self._seen: dict[tuple[str, str], int] = {}

    # ---------- text helpers ----------

    def _text(self, node, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _node_text(self, node, source: bytes, up_to=None) -> str:
        """Text from `node` start up to (not including) `up_to`, or the whole node."""
        end = up_to.start_byte if up_to else node.end_byte
        return source[node.start_byte:end].decode("utf-8", errors="replace").rstrip()

    def _find_body(self, node):
        return next((c for c in node.children if c.type in self.config.body_types), None)

    def _sig_line(self, inner, source: bytes) -> str:
        """The 'class X(...):' / 'class Foo {' line — everything before the body block."""
        body = self._find_body(inner)
        if body is None:
            return self._text(inner, source)
        return self._node_text(inner, source, up_to=body)

    def _leading_docs(self, node, source: bytes) -> tuple[str, int] | None:
        """Comment / attribute siblings directly above a def, if any.

        Doc comments (JS/TS/Java/C++/Swift `/** ... */`, Python `#`) and Rust
        attributes (`#[derive(Debug)]`) belong with the symbol they document;
        fold them into the chunk text and report range. Only comments that are
        *adjacent* (no more than one blank line) are collected, so a file
        header or a comment separated by several blank lines isn't glued to
        the first def below it.
        """
        parts: list[str] = []
        start_line = None
        prev = node.prev_named_sibling
        while prev is not None and prev.type in self.config.leading_types:
            if node.start_point[0] - prev.end_point[0] > 1:
                break  # separated by a blank line (or more) — not this def's docs
            parts.append(self._text(prev, source))
            start_line = prev.start_point[0] + 1
            node = prev
            prev = prev.prev_named_sibling
        if not parts:
            return None
        parts.reverse()
        return "\n".join(parts), start_line

    # ---------- name helpers ----------

    def _unwrap(self, node):
        """Look through wrapper_types (and single-def container_types) to
        reach the real definition node.

        Returns None if a wrapper does not actually contain a definition
        (e.g. `export const x = 1` — handled separately by
        `_unwrap_declaration`).
        """
        while node.type in self.config.wrapper_types or node.type in self.config.container_types:
            inner = next((c for c in node.children if c.type in self.config.def_types), None)
            if inner is None:
                return None
            node = inner
        return node

    def _unwrap_declaration(self, node):
        """Look through wrappers to a declaration container (JS/TS
        `export const foo = () => {}`), or None."""
        while node.type in self.config.wrapper_types:
            inner = next((c for c in node.children if c.type in self.config.declaration_types), None)
            if inner is None:
                return None
            node = inner
        return node if node.type in self.config.declaration_types else None

    def _name(self, node, source: bytes) -> str:
        if self.config.name_field is not None:
            named = node.child_by_field_name(self.config.name_field)
            if named is not None:
                return self._text(named, source)
        if self.config.name_fn is not None:
            found = self.config.name_fn(node, source)
            if found is not None:
                return found
        return self._find_name(node, source)

    def _find_name(self, node, source: bytes) -> str:
        matches: list[str] = []
        for child in node.children:
            if child.type in self.config.name_skip_types:
                continue
            if child.type in self.config.name_in_types:
                found = self._find_name(child, source)
                if found != "<anonymous>":
                    matches.append(found)
                continue
            if child.type in self.config.name_types:
                matches.append(self._text(child, source))
        if not matches:
            return "<anonymous>"
        return matches[0]

    # ---------- chunk builders ----------

    def _chunk(self, node, source: bytes, file_path: str, name: str, node_type: str) -> Chunk:
        """Build a chunk for the (possibly wrapped) def node `node`."""
        text = self._text(node, source)
        start_line = node.start_point[0] + 1
        docs = self._leading_docs(node, source)
        if docs:
            text, start_line = f"{docs[0]}\n{text}", docs[1]
        return Chunk(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{node_type}:{name}")),
            text=text,
            file_path=file_path,
            node_type=node_type,
            name=name,
            start_line=start_line,
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

    def _unique(self, node_type: str, name: str) -> str:
        """Deterministic disambiguation for repeated names.

        Overloads (Java/C#/C++ methods, Kotlin functions) and duplicate
        Rust impl blocks would otherwise collide on the chunk id (which is
        keyed on file:node_type:name) and silently overwrite each other in
        Qdrant. Second occurrence of a (node_type, name) pair becomes
        name#2, name#3, ... — stable across re-ingestion.
        """
        key = (node_type, name)
        count = self._seen.get(key, 0)
        if count:
            self._seen[key] = count + 1
            return f"{name}#{count + 1}"
        self._seen[key] = 1
        return name

    def _skeleton_chunk(self, node, inner, body, source, file_path, name) -> Chunk:
        """Header chunk for a class-like split into members: leading doc
        comment + decorators/wrapper prefix + signature line + class-level
        fields/attrs. Member bodies are intentionally excluded."""
        parts: list[str] = []
        start_line = node.start_point[0] + 1
        docs = self._leading_docs(node, source)
        if docs:
            parts.append(docs[0])
            start_line = docs[1]
        prefix = self._node_text(node, source, up_to=inner)
        if prefix:
            parts.append(prefix)
        parts.append(self._sig_line(inner, source))
        if body is not None:
            for child in body.children:
                if child.type in self.config.header_member_types:
                    parts.append(self._node_text(child, source))

        text = "\n".join(p for p in parts if p)
        end_line = body.children[0].start_point[0] + 1 if body is not None and body.children else node.end_point[0] + 1
        return self._chunk_from_text(
            text, file_path, name=name, node_type="class_header",
            start_line=start_line, end_line=end_line,
        )

    # ---------- main walk ----------

    def chunk_file(self, file_path: str) -> list[Chunk]:
        source = Path(file_path).read_bytes()
        root = self.parser.parse(source).root_node
        self._seen = {}
        return self._walk_children(root.children, source, str(file_path), qualifier="", in_class=False)

    def _walk_children(self, children, source: bytes, file_path: str, qualifier: str, in_class: bool) -> list[Chunk]:
        chunks: list[Chunk] = []
        for node in children:
            if node.type in self.config.container_types:
                chunks.extend(self._chunk_container(node, source, file_path, qualifier, in_class))
            elif node.type in self.config.scope_types:
                chunks.extend(self._chunk_scope(node, source, file_path, qualifier, in_class))
            elif node.type in self.config.declaration_types:
                chunks.extend(self._chunk_declarations(node, source, file_path, qualifier, in_class))
            elif node.type in self.config.def_types:
                chunks.extend(self._def_chunk(node, source, file_path, qualifier, in_class))
        return chunks

    def _chunk_declarations(self, node, source: bytes, file_path: str, qualifier: str, in_class: bool) -> list[Chunk]:
        """Chunk JS/TS `const foo = () => {...}` declarations.

        Only declarators whose value is a function (arrow / function
        expression) become chunks — plain constants (`const x = 5`) would be
        noise. `export const foo = () => {}` is reached through `_def_chunk`'s
        `_unwrap_declaration` fallback.
        """
        chunks: list[Chunk] = []
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            value = child.child_by_field_name("value")
            if value is None or value.type not in self.config.function_value_types:
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None or name_node.type != "identifier":
                continue  # destructuring patterns have no single name
            name = self._text(name_node, source)
            if qualifier and name != "<anonymous>":
                name = f"{qualifier}.{name}"
            name = self._unique("function_declaration", name)
            node_type = "method_definition" if in_class else "function_definition"
            chunks.append(self._chunk(child, source, file_path, name, node_type))
        return chunks

    def _chunk_container(self, node, source, file_path, qualifier, in_class) -> list[Chunk]:
        """A def that wraps one OR several inner defs (Go `type ( ... )`)."""
        defs = [c for c in node.children if c.type in self.config.def_types]
        if len(defs) == 1:
            # single inner def — chunk the whole node so prefix text ("type ") is kept
            return self._def_chunk(node, source, file_path, qualifier, in_class)
        chunks = []
        for d in defs:
            chunks.extend(self._def_chunk(d, source, file_path, qualifier, in_class))
        return chunks

    def _chunk_scope(self, node, source, file_path, qualifier, in_class) -> list[Chunk]:
        """A namespace/module: recurse into its body, qualifying member names.

        The scope's own leading docs (e.g. Rust `#[cfg(test)]` on a mod) are
        folded into its first member chunk so they aren't lost.
        """
        inner = self._unwrap(node)
        if inner is None:
            return []
        name = self._name(inner, source)
        if name != "<anonymous>":
            q = f"{qualifier}.{name}" if qualifier else name
        else:
            q = qualifier
        body = self._find_body(inner)
        if body is None:
            return []
        chunks = self._walk_children(body.children, source, file_path, q, in_class)
        docs = self._leading_docs(node, source)
        if docs and chunks:
            first = chunks[0]
            chunks[0] = self._chunk_from_text(
                f"{docs[0]}\n{first.text}", first.file_path,
                name=first.name, node_type=first.node_type,
                start_line=docs[1], end_line=first.end_line,
            )
        return chunks

    def _def_chunk(self, node, source, file_path, qualifier, in_class) -> list[Chunk]:
        inner = self._unwrap(node)
        if inner is None:
            decl = self._unwrap_declaration(node)
            if decl is not None:
                return self._chunk_declarations(decl, source, file_path, qualifier, in_class)
            # wrapper around something that isn't a definition (export const x = 1)
            return []
        if inner.type in self.config.scope_types:
            # a wrapped scope (defensive — none of the current configs wrap one)
            return self._chunk_scope(node, source, file_path, qualifier, in_class)

        name = self._name(inner, source)
        if qualifier and name != "<anonymous>":
            name = f"{qualifier}.{name}"
        name = self._unique(inner.type, name)

        if inner.type in self.config.class_types:
            if in_class:
                # nested class-like — kept whole (matches the original Python chunker)
                return [self._chunk(node, source, file_path, name, "nested_class_definition")]
            body = self._find_body(inner)
            members: list[Chunk] = []
            if body is not None:
                members = self._walk_children(body.children, source, file_path, name, in_class=True)
            if members:
                header = self._skeleton_chunk(node, inner, body, source, file_path, name)
                return [header] + members
            return [self._chunk(node, source, file_path, name, inner.type)]

        if inner.type in self.config.always_method_types:
            node_type = "method_definition"
        elif inner.type in self.config.method_types:
            node_type = "method_definition" if in_class else "function_definition"
        else:
            node_type = inner.type
        return [self._chunk(node, source, file_path, name, node_type)]


# ---------- language registry ----------

def _load_language(module_name: str, accessor: str = "language") -> Language | None:
    """Import a tree-sitter grammar binding; None if the package is missing."""
    try:
        module = importlib.import_module(module_name)
        return Language(getattr(module, accessor)())
    except Exception:
        return None


def _typescript_config(name: str, extensions: tuple[str, ...], language: Language) -> LanguageConfig:
    return LanguageConfig(
        name=name, extensions=extensions, language=language,
        def_types=frozenset({
            "function_declaration", "generator_function_declaration",
            "class_declaration", "method_definition", "method_signature",
            "interface_declaration", "enum_declaration",
            "type_alias_declaration", "abstract_class_declaration",
            "export_statement",
        }),
        class_types=frozenset({
            "class_declaration", "interface_declaration", "enum_declaration",
            "type_alias_declaration", "abstract_class_declaration",
        }),
        body_types=frozenset({"class_body", "interface_body", "enum_body"}),
        name_types=frozenset({
            "identifier", "property_identifier", "private_property_identifier", "type_identifier",
        }),
        wrapper_types=frozenset({"export_statement"}),
        declaration_types=frozenset({"lexical_declaration", "variable_declaration"}),
        method_types=frozenset({"method_definition", "method_signature"}),
        header_member_types=frozenset({
            "field_definition", "public_field_definition", "property_signature",
        }),
    )


def _build_configs() -> dict[str, LanguageConfig]:
    """extension (lowercase, with dot) -> LanguageConfig. A grammar package
    that isn't installed just doesn't register its language."""
    configs: dict[str, LanguageConfig] = {}

    def register(config: LanguageConfig) -> None:
        for ext in config.extensions:
            configs[ext] = config

    py = _load_language("tree_sitter_python")
    if py:
        register(LanguageConfig(
            name="python", extensions=(".py",), language=py,
            def_types=frozenset({
                "function_definition", "async_function_definition",
                "class_definition", "decorated_definition",
            }),
            class_types=frozenset({"class_definition"}),
            body_types=frozenset({"block"}),
            name_types=frozenset({"identifier"}),
            wrapper_types=frozenset({"decorated_definition"}),
            method_types=frozenset({
                "function_definition", "async_function_definition", "decorated_definition",
            }),
            header_member_types=frozenset({"expression_statement"}),
        ))

    js = _load_language("tree_sitter_javascript")
    if js:
        register(LanguageConfig(
            name="javascript", extensions=(".js", ".jsx", ".mjs", ".cjs"), language=js,
            def_types=frozenset({
                "function_declaration", "generator_function_declaration",
                "class_declaration", "method_definition", "export_statement",
            }),
            class_types=frozenset({"class_declaration"}),
            body_types=frozenset({"class_body"}),
            name_types=frozenset({
                "identifier", "property_identifier", "private_property_identifier", "type_identifier",
            }),
            wrapper_types=frozenset({"export_statement"}),
            declaration_types=frozenset({"lexical_declaration", "variable_declaration"}),
            method_types=frozenset({"method_definition"}),
            header_member_types=frozenset({"field_definition", "public_field_definition"}),
        ))

    ts = _load_language("tree_sitter_typescript", "language_typescript")
    if ts:
        register(_typescript_config("typescript", (".ts", ".mts", ".cts"), ts))

    tsx = _load_language("tree_sitter_typescript", "language_tsx")
    if tsx:
        register(_typescript_config("typescript_react", (".tsx",), tsx))

    java = _load_language("tree_sitter_java")
    if java:
        register(LanguageConfig(
            name="java", extensions=(".java",), language=java,
            def_types=frozenset({
                "class_declaration", "interface_declaration", "enum_declaration",
                "record_declaration", "annotation_type_declaration",
                "method_declaration", "constructor_declaration",
            }),
            class_types=frozenset({
                "class_declaration", "interface_declaration", "enum_declaration",
                "record_declaration", "annotation_type_declaration",
            }),
            body_types=frozenset({"class_body"}),
            name_types=frozenset({"identifier"}),
            name_skip_types=frozenset({"modifiers", "marker_annotation", "annotation"}),
            method_types=frozenset({"method_declaration", "constructor_declaration"}),
            header_member_types=frozenset({"field_declaration", "enum_constant"}),
        ))

    go = _load_language("tree_sitter_go")
    if go:
        register(LanguageConfig(
            name="go", extensions=(".go",), language=go,
            def_types=frozenset({
                "function_declaration", "method_declaration",
                "type_declaration", "type_spec",
            }),
            class_types=frozenset({"type_spec"}),
            body_types=frozenset(),
            name_types=frozenset({"identifier", "field_identifier", "type_identifier"}),
            name_skip_types=frozenset({"parameter_list"}),  # the receiver
            container_types=frozenset({"type_declaration"}),
            method_types=frozenset({"function_declaration"}),
            always_method_types=frozenset({"method_declaration"}),
        ))

    rust = _load_language("tree_sitter_rust")
    if rust:
        register(LanguageConfig(
            name="rust", extensions=(".rs",), language=rust,
            def_types=frozenset({
                "function_item", "function_signature_item", "struct_item", "enum_item",
                "impl_item", "trait_item", "mod_item", "type_item",
                "const_item", "static_item", "union_item",
            }),
            class_types=frozenset({
                "struct_item", "enum_item", "impl_item", "trait_item",
                "type_item", "union_item",
            }),
            body_types=frozenset({"declaration_list", "field_declaration_list", "enum_variant_list"}),
            name_types=frozenset({"identifier", "type_identifier"}),
            name_skip_types=frozenset({"type_parameters"}),
            name_in_types=frozenset({"type", "path", "generic_type"}),
            scope_types=frozenset({"mod_item"}),
            method_types=frozenset({"function_item", "function_signature_item"}),
            header_member_types=frozenset({"field_declaration"}),
            leading_types=frozenset({"comment", "attribute_item"}),
        ))

    c = _load_language("tree_sitter_c")
    if c:
        register(LanguageConfig(
            name="c", extensions=(".c", ".h"), language=c,
            def_types=frozenset({
                "function_definition", "struct_specifier",
                "enum_specifier", "union_specifier", "typedef_declaration",
            }),
            class_types=frozenset({"struct_specifier", "enum_specifier", "union_specifier"}),
            body_types=frozenset({"field_declaration_list"}),
            name_types=frozenset({"identifier", "type_identifier"}),
            name_fn=_declarator_name,
        ))

    cpp = _load_language("tree_sitter_cpp")
    if cpp:
        register(LanguageConfig(
            name="cpp", extensions=(".cc", ".cpp", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".ipp"),
            language=cpp,
            def_types=frozenset({
                "function_definition", "class_specifier", "struct_specifier",
                "union_specifier", "enum_specifier", "typedef_declaration",
                "template_declaration",
            }),
            class_types=frozenset({
                "class_specifier", "struct_specifier", "union_specifier", "enum_specifier",
            }),
            body_types=frozenset({"field_declaration_list", "declaration_list"}),
            name_types=frozenset({
                "identifier", "field_identifier", "type_identifier", "namespace_identifier",
            }),
            name_fn=_declarator_name,
            wrapper_types=frozenset({"template_declaration"}),
            scope_types=frozenset({"namespace_definition"}),
            method_types=frozenset({"function_definition"}),
            header_member_types=frozenset({"field_declaration"}),
        ))

    csharp = _load_language("tree_sitter_c_sharp")
    if csharp:
        register(LanguageConfig(
            name="c_sharp", extensions=(".cs",), language=csharp,
            def_types=frozenset({
                "class_declaration", "interface_declaration", "struct_declaration",
                "record_declaration", "enum_declaration", "method_declaration",
                "constructor_declaration", "namespace_declaration",
            }),
            class_types=frozenset({
                "class_declaration", "interface_declaration", "struct_declaration",
                "record_declaration", "enum_declaration",
            }),
            body_types=frozenset({"declaration_list"}),
            name_types=frozenset({"identifier"}),
            name_field="name",
            scope_types=frozenset({"namespace_declaration"}),
            method_types=frozenset({"method_declaration", "constructor_declaration"}),
            header_member_types=frozenset({
                "field_declaration", "property_declaration", "event_declaration",
            }),
        ))

    ruby = _load_language("tree_sitter_ruby")
    if ruby:
        register(LanguageConfig(
            name="ruby", extensions=(".rb",), language=ruby,
            def_types=frozenset({"method", "singleton_method", "class", "module"}),
            class_types=frozenset({"class"}),
            body_types=frozenset({"body_statement"}),
            name_types=frozenset({"identifier", "constant", "constant_path"}),
            scope_types=frozenset({"module"}),
            method_types=frozenset({"method", "singleton_method"}),
        ))

    php = _load_language("tree_sitter_php", "language_php")
    if php:
        register(LanguageConfig(
            name="php", extensions=(".php",), language=php,
            def_types=frozenset({
                "function_definition", "class_declaration", "method_declaration",
                "interface_declaration", "trait_declaration", "enum_declaration",
            }),
            class_types=frozenset({
                "class_declaration", "interface_declaration",
                "trait_declaration", "enum_declaration",
            }),
            body_types=frozenset({"declaration_list"}),
            name_types=frozenset({"name"}),
            scope_types=frozenset({"namespace_definition"}),
            method_types=frozenset({"method_declaration", "function_definition"}),
            header_member_types=frozenset({"property_declaration", "const_declaration"}),
        ))

    kotlin = _load_language("tree_sitter_kotlin")
    if kotlin:
        register(LanguageConfig(
            name="kotlin", extensions=(".kt", ".kts"), language=kotlin,
            def_types=frozenset({
                "function_declaration", "class_declaration", "object_declaration",
                "interface_declaration", "constructor_declaration",
            }),
            class_types=frozenset({
                "class_declaration", "object_declaration", "interface_declaration",
            }),
            body_types=frozenset({"class_body"}),
            name_types=frozenset({"identifier"}),
            method_types=frozenset({"function_declaration", "constructor_declaration"}),
        ))

    swift = _load_language("tree_sitter_swift")
    if swift:
        register(LanguageConfig(
            name="swift", extensions=(".swift",), language=swift,
            def_types=frozenset({
                "function_declaration", "function_signature", "initializer_declaration",
                "class_declaration", "struct_declaration", "enum_declaration",
                "protocol_declaration", "extension_declaration", "actor_declaration",
            }),
            class_types=frozenset({
                "class_declaration", "struct_declaration", "enum_declaration",
                "protocol_declaration", "extension_declaration", "actor_declaration",
            }),
            body_types=frozenset({"class_body"}),
            name_types=frozenset({"simple_identifier", "type_identifier"}),
            method_types=frozenset({"function_declaration", "function_signature", "initializer_declaration"}),
        ))

    return configs


_CONFIGS: dict[str, LanguageConfig] = _build_configs()
_CHUNKERS: dict[int, CodeChunker] = {id(cfg): CodeChunker(cfg) for cfg in set(_CONFIGS.values())}
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(_CONFIGS)


def get_chunker_for(extension: str) -> CodeChunker | None:
    """The chunker for a file extension (".py", ".rs", ...), or None."""
    return _CHUNKERS.get(id(_CONFIGS.get(extension.lower())))


def chunk_file(file_path: str) -> list[Chunk]:
    """Chunk a source file, dispatching on its file extension.

    Raises ValueError for unsupported extensions.
    """
    ext = Path(file_path).suffix.lower()
    chunker = get_chunker_for(ext)
    if chunker is None:
        raise ValueError(
            f"Unsupported file extension '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return chunker.chunk_file(file_path)


class PythonChunker(CodeChunker):
    """Backward-compatible name for the Python chunker (kept for existing
    callers and tests — the dispatcher is `chunk_file`)."""

    def __init__(self):
        super().__init__(_CONFIGS[".py"])
