# Run 05 — Multi-language code chunker (no benchmark — feature/infra change)

**Date:** 2026-08-12
**Command:** `./.venv/Scripts/python.exe test_pipeline.py` (offline suite — no API keys, no server)
**Score:** n/a — no RAGAS/50-question run. The benchmark (`benchmarks/evals.jsonl`) is a
Python-only set about the `rich` codebase, so there is no comparable multi-language score to
measure. The offline test suite is the verification gate for this change.

---

## 1. What changed

`app/chunking.py` went from a Python-only `PythonChunker` to a **config-driven multi-language
chunker** (`CodeChunker` + a `LanguageConfig` registry). Same chunking philosophy as before —
chunk the way a reader browses a file:

- every **function-like definition** is one chunk (`function_definition` at top level,
  `method_definition` inside a class body),
- every **class-like definition with members** (class/struct/interface/enum/impl/trait) is split
  into a **`class_header`** chunk (leading doc comment + decorators + signature line + class-level
  fields) plus one chunk per member,
- namespaces/modules (`namespace`, `mod`, `module`, C# `namespace`, PHP `namespace`) are *scopes*:
  no chunk of their own, but every member name is qualified (`App.Greeter.Greet`).

**Languages now supported (13 + Python):** JavaScript (`.js/.jsx/.mjs/.cjs`), TypeScript
(`.ts/.mts/.cts`), TSX (`.tsx`), Java, Go, Rust, C (`.c/.h`), C++ (`.cc/.cpp/.cxx/.c++/…`),
C#, Ruby, PHP, Kotlin (`.kt/.kts`), Swift. Extension → language dispatch via
`chunking.chunk_file(path)`; unknown extensions raise a clear `ValueError`.

### Per-language quirks handled (verified against the real grammars)
| Language | Trick |
|----------|-------|
| JS/TS/TSX | `export_statement` unwraps to the real def; TS `interface_body`/`enum_body` bodies; `method_signature`/`property_signature` interface members |
| Java | skips the `modifiers` subtree when finding names (return types and annotations are not the name) |
| Go | receiver `parameter_list` skipped for method names; grouped `type ( … )` declarations split per `type_spec` |
| Rust | `#[derive(Debug)]`-style `attribute_item` is folded into the chunk text as leading docs; impl blocks split into header + methods; duplicate `impl Foo` blocks get distinct ids |
| C/C++ | function names live in the `declarator` field chain — custom `_declarator_name` handles `int *foo()`, `void Foo::bar()` → `bar`; `template_declaration` and `namespace_definition` unwrap/scope correctly |
| C# | name comes from the `name` *field* (not the return type); class/namespace bodies are both `declaration_list` |
| Ruby | `module` is a scope (so `module Foo; class Bar` → `Foo.Bar.greet`), `class` splits normally |
| PHP | method names are `name` nodes; `namespace App;` (semicolon form) degrades gracefully |
| Kotlin/Swift | names are `identifier` / `simple_identifier` respectively |

### Two generic behaviors worth knowing
1. **Leading docs are folded into the chunk**: a `comment` (doc comment in any language) directly
   above a def is prepended to that chunk's text (and its line range). Rust also collects
   `attribute_item` siblings. This is a small behavioral change for Python too — `# comment` above
   a class now lands in the header chunk text. **Chunk ids are unchanged** (still
   `uuid5(file:node_type:name)`), so existing Qdrant collections re-ingest without duplicating —
   the text of existing points will just update on re-run.
2. **Deterministic id dedup for repeated names**: overloads (Java/C#/C++/Kotlin methods) and
   duplicate Rust impl blocks would collide on `(file, node_type, name)` ids and silently
   overwrite each other in Qdrant. The second occurrence gets a stable `name#2` suffix.

### Ingestion (`app/ingestion.py`)
- Walks **all supported extensions** (no more `*.py` hard-code); prints a per-extension file count.
- **Skips vendored/build/tooling dirs** (`node_modules`, `.venv`, `venv`, `dist`, `build`, `target`,
  `Pods`, …) — critical now that JS/TS/etc. drag in vendor trees.
- New `--langs py,js,ts` flag to restrict ingestion by extension.

### Dependencies
`pyproject.toml` (+ `requirements.txt`): added the 12 grammar wheels
(`tree-sitter-javascript`, `tree-sitter-typescript`, `tree-sitter-java`, `tree-sitter-go`,
`tree-sitter-rust`, `tree-sitter-c`, `tree-sitter-cpp`, `tree-sitter-c-sharp`, `tree-sitter-ruby`,
`tree-sitter-php`, `tree-sitter-kotlin`, `tree-sitter-swift`). All ship abi3 Windows wheels, so
Python 3.14 is fine. **Grammars are loaded lazily**: a language whose package isn't installed is
simply not registered — partial installs still work.

---

## 2. Verification

`test_pipeline.py` (offline, no keys) — all checks green:

```
OK: multi-language chunker covers 13 languages (+ Python)
OK: repeated names (overloads/impls) get distinct, stable ids
```

New tests:
- `_check_multilang_chunker` — per-language sample files chunked through the extension registry;
  asserts the class chunk, the `method_definition` chunk, and **stable ids across re-chunking**.
  Also asserts `PythonChunker()` (the old name) still works and produces identical ids to the
  dispatcher.
- `_check_chunker_dedup` — Java overloads (`A.f` / `A.f#2`) and duplicate Rust impls (`A.go` /
  `A#2.go`) get distinct, stable ids.

Smoke-probed all 14 variants by hand against real grammar parses before wiring the configs
(interface bodies, Go receivers, C declarator chains, Swift `simple_identifier`, PHP `name`, …).

---

## 3. Notes / observations

1. **No benchmark yet** — building a multi-language eval set (questions + expected answers for
   non-Python codebases) is a separate project; the current 20-question set can't score this.
2. **Node type vocabulary grew on purpose**: class-like chunks keep the *language's* node type
   (`struct_item`, `interface_declaration`, `impl_item`, …) instead of collapsing to
   `class_definition` — more signal for the LLM prompt and the BM25/vector indices, and ids stay
   per-language unique.
3. **PHP `namespace App;` (semicolon form)** has no parse-tree body, so members aren't
   namespace-qualified — they're still chunked, just unqualified. Braced namespaces are fine.
4. **Files in non-UTF-8 encodings** decode with `errors="replace"` — a mangled character is
   better than losing the whole file, and parse/name extraction are byte-based anyway.
5. **Re-ingestion is idempotent**: ids are name-keyed, not line-keyed, so a re-run updates in
   place (same behavior as the Python-only chunker).

---

## 4. Open items / future ideas

| # | Idea | Notes |
|---|------|-------|
| 1 | **Multi-language eval set** (per-language repos + questions) so this feature gets a real score | highest impact next step |
| 2 | Qualify PHP `namespace App;` members with the namespace name | parser limitation workaround needed |
| 3 | Include Java `enum_constant`s / C# `enum_member_declaration`s as first-class chunks | currently folded into the class header |
| 4 | Optionally persist per-language stats at ingestion (chunk counts by node_type) | diagnostics |
