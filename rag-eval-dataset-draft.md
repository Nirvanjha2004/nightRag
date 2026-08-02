# NightCode RAG Golden Evaluation Dataset — Draft v1

**Repo:** [NightCode] (this repo)
**Status:** DRAFT — every answer must be manually verified before use as ground truth.
**Line numbers:** captured 2026-08-02 via `grep -n` against the working tree. If you've edited files since, re-verify.
**Answer format:** `file path` → `function/class` → `line range`.

---

## Confidence legend

- **HIGH** — I read the exact code; line ranges verified by grep; logic unambiguous.
- **MEDIUM** — logic verified, but either the line range is estimated, external behavior (LLM/API) is involved, or a subtle detail could change the "best" answer.
- **LOW / FLAG** — include only because it's a good eval trap; current answer is shaky (dead code, unverified path, or likely-wrong behavior).

All answers point at the *primary* location the question should map to. For multi-file questions, the first entry is the anchor; additional files are listed as supporting evidence.

---

## Category 1 — "Where is X implemented" (direct lookups)

### Q1. Where is the bash tool implemented?
- **Answer:** `packages/cli/src/agent/tools.ts` → `bash` (Tool object) → **609–679**
- **Notes:** Includes shell selection (powershell.exe on win32), timeout sanitization/clamping (610–620), `execAsync` with `shell`/`timeout`/`maxBuffer`/`windowsHide`.
- **Confidence:** HIGH

### Q2. Where is the destructive-command detection for the bash tool?
- **Answer:** `packages/cli/src/agent/tools.ts` → `isDestructiveCommand` → **107–110** (pattern list `DESTRUCTIVE_PATTERNS` at **80–105**)
- **Notes:** Also referenced by `bash.isDestructive` (~line 610). The *pause* itself lives in `AgentLoop.execute` (see Q13/Q27).
- **Confidence:** HIGH

### Q3. Where is the context-window compression / summarization implemented?
- **Answer:** `packages/cli/src/agent/context.ts` → `manageContextWindow` → **261–315**
- **Notes:** Threshold const `CONTEXT_THRESHOLD_TOKENS` = 100_000 (line 188), preserves last 15 messages (189).
- **Confidence:** HIGH

### Q4. Where is the slash-command filtering logic?
- **Answer:** `packages/cli/components/commands-menu/filter-commands.ts` → `getFiltererdCommands` → **4–7**
- **Notes:** Function name has a typo ("Filtererd") — good hallucination trap for the eval. Prefix `startsWith` match on `command.value`.
- **Confidence:** HIGH

### Q5. Where is the agent's main execution loop?
- **Answer:** `packages/cli/src/agent/loop.ts` → `AgentLoop.execute` → **15–292** (class `AgentLoop` **8–342**)
- **Notes:** Iteration loop `for (let iter = 1; iter <= maxIterations; iter++)` at line 50.
- **Confidence:** HIGH

### Q6. Where is semantic search over past events (episodic retrieval) implemented?
- **Answer:** `packages/cli/src/agent/memory/EpisodicMemoryManager.ts` → `retrieveRelevantMemories` → **102–118**
- **Notes:** Embedding via `getEmbedding` (31–51, Jina API), scoring via `cosineSimilarity` (89–100).
- **Confidence:** HIGH

---

## Category 2 — "How does X work" (2–3 related functions)

### Q7. How does a tool call get executed and its args stored back into chat history?
- **Answer:** `packages/cli/src/agent/loop.ts` → tool-execution block inside `AgentLoop.execute` → **~155–255**; key helper `trimToolCallArgsForHistory` → **232–250**; wire-format mapping in `GroqClient.callGroq` → `packages/cli/src/llm-client/groq-client.ts` → **60–227**
- **Notes:** Executes each toolCall inside a `tool.<name>` span, coerces result to string, then stores an assistant message with args trimmed to 300 chars per string value so the 4k-char args don't flood history.
- **Confidence:** HIGH (logic verified; the ~155–255 outer range is approximate — the exact exec/catch lines are 155–230)

### Q8. How does the agent decide what to remember after a finished task?
- **Answer:** `packages/cli/src/agent/agent-harness.ts` → `AgentHarness.onTaskComplete` → **135–254** → `extractMemories` in `packages/cli/src/agent/memory/memoryClassifier.ts` → **24–83**
- **Notes:** Trace → LLM (llama-3.1-8b-instant, temp 0, `response_format: json_object`) → splits into semantic/procedural/episodic → persisted via the three managers.
- **Confidence:** HIGH

### Q9. How is memory context assembled for each turn?
- **Answer:** `packages/cli/src/agent/agent-harness.ts` → `AgentHarness.buildMemoryContext` → **39–133** → injected by `ContextBuilder.build` in `packages/cli/src/agent/context.ts` → **333–386** (appended to systemPrompt, ~line 378)
- **Notes:** Semantic facts + procedural rules + top-5 episodic retrievals; built ONCE per user turn in `AgentLoop.execute` (loop.ts:36–49), not per iteration.
- **Confidence:** HIGH

### Q10. How does the summarizer avoid losing earlier context across repeated compressions?
- **Answer:** `packages/cli/src/agent/context.ts` → `manageContextWindow` → **261–315**, with per-session summary cache `sessionSummaries` (class field at **322**, read/written in `build` at **347–352**)
- **Notes:** New summary is chained to the existing one (`combinedSummary`, ~line 281). ⚠️ Subtlety worth verifying: `build` always re-runs `manageContextWindow` over *all* rawMessages, so old messages appear to be re-summarized (and re-chained) on every over-threshold call — the stored `summarizedUpToMessageId` field (352) is written but never read to skip work. The "no loss" claim holds, but the dedup optimization looks unused.
- **Confidence:** MEDIUM

### Q11. How does the grep tool run ripgrep safely?
- **Answer:** `packages/cli/src/agent/tools.ts` → `buildRipgrepArgs` → **469–493** → `runProcess` → **498–528** → `grep` (Tool) → **530–573**
- **Notes:** No shell (spawn with argv → no quoting/escaping issues), `--` terminator so patterns starting with `-` are treated as text, `-g !**/memory/**` always excludes memory/, maxResults clamped to 1000, 10MB buffer cap + SIGKILL on timeout.
- **Confidence:** HIGH

### Q12. How does the LLM client recover when the model messes up tool calling?
- **Answer:** `packages/cli/src/llm-client/groq-client.ts` → `GroqClient.chat` → **20–59**
- **Notes:** On error code `tool_use_failed`, retries once with a repair prompt appended ("Use ONLY the native tool calling interface / Never emit XML/JSON tool calls"). ⚠️ Relies on Groq surfacing that exact error code — end-to-end behavior unverified here.
- **Confidence:** MEDIUM

---

## Category 3 — Vague / natural-language questions

### Q13. "I asked the agent to delete a file — what protects me before it actually happens?"
- **Answer:** `packages/cli/src/agent/tools.ts` → `del` (Tool) → **299–330** (`destructive: true` at ~line 302) + confirmation gate in `packages/cli/src/agent/loop.ts` → `AgentLoop.execute` → **184–197**
- **Notes:** Static `destructive: true` flag triggers `confirmHook`; if the user rejects, the tool is never executed.
- **Confidence:** HIGH

### Q14. "What keeps the AI out of the folder where it stores what it remembers?"
- **Answer:** `packages/cli/src/agent/tools.ts` → `assertNotMemoryPath` → **55–63** (regex `MEMORY_PATH_PATTERN` at **53**), plus the `-g !**/memory/**` exclusion inside `buildRipgrepArgs` → **469–493**
- **Notes:** Called by every file-touching tool's exec; ripgrep additionally never surfaces memory/ contents.
- **Confidence:** HIGH

### Q15. "Where does the chat history for a conversation live?"
- **Answer:** `packages/cli/src/agent/messages.ts` → `MessageManager` → **4–39**
- **Notes:** In-memory `Map<sessionId, MessageType[]>`; keyed per session. Not persisted to disk.
- **Confidence:** HIGH

### Q16. "What shows on screen while the agent is working?"
- **Answer:** `packages/cli/src/index.tsx` → `ThinkingIndicator` → **105–122** (animated `Thinking...` dots), rendered from `App`'s loading branch → **312–317**
- **Confidence:** HIGH

### Q17. "What happens if the agent tries to use a tool that doesn't exist?"
- **Answer:** `packages/cli/src/agent/loop.ts` → `AgentLoop.execute` unknown-tool branch → **163–172**
- **Notes:** `toolRegistry.get` returns undefined → result set to `Error: Tool "x" is not registered.`, span marked error, no throw — the model sees the error as a normal tool result.
- **Confidence:** HIGH

### Q18. "How does the app know which model it's talking to?"
- **Answer:** `packages/cli/src/agent/session.ts` → `SessionManager.create` → **8–17** (stores `model` on the session) + session created in `packages/cli/src/main.ts` → **~96–101** (`model: "qwen/qwen3.6-27b"`) + displayed by `StatusBar` → `packages/cli/components/status-bar.tsx` → **16–41**
- **Notes:** Single model is hardcoded at session creation in main.ts; `GroqClient.callGroq` sends `context.model` to the API.
- **Confidence:** MEDIUM-HIGH (plumbing is clear; exact main.ts lines for session creation are ~96–101 — re-check)

---

## Category 4 — Edge cases / error handling

### Q19. What happens if a shell command hangs or dumps a huge amount of output?
- **Answer:** `packages/cli/src/agent/tools.ts` → constants `SHELL_TIMEOUT_MS`/`SHELL_MAX_BUFFER` → **29–30**; `runProcess` → **498–528** (SIGKILL on timeout, buffer-cap kill at ~512); `truncate` → **120–124** (head + last 3,000 chars tail, with marker)
- **Notes:** Timeout 120s, buffer 10MB; a huge log is head+tail truncated so failures at the end stay visible.
- **Confidence:** HIGH

### Q20. What happens if the summarizer LLM call fails?
- **Answer:** `packages/cli/src/agent/context.ts` → `summarizeMessages` → **224–259** (fallback in catch → truncated concat, **~252–259**)
- **Notes:** Graceful degradation: logs the error, returns a raw truncated concatenation instead of losing compression entirely.
- **Confidence:** HIGH

### Q21. What happens when a tool throws an exception during execution?
- **Answer:** `packages/cli/src/agent/loop.ts` → `AgentLoop.execute` tool catch block → **~200–212**
- **Notes:** `result = "Error: ${errMsg}"` returned to the model (not thrown), span marked error via `markSpanError`, `tool.success=false`.
- **Confidence:** HIGH on logic / MEDIUM on exact line range (catch block sits inside the tool span, ~200–212)

### Q22. What happens if the user rejects a destructive action?
- **Answer:** `packages/cli/src/agent/loop.ts` → `AgentLoop.execute` rejection branch → **192–196**
- **Notes:** Result becomes `User rejected the X operation. Inform them and do not retry unless asked.`; tool is not executed; span marked unsuccessful; loop continues.
- **Confidence:** HIGH

### Q23. What happens if the agent runs out of iterations without answering?
- **Answer:** `packages/cli/src/agent/loop.ts` → `AgentLoop.execute` max-iterations → **271–283** (throw at **282**)
- **Notes:** Logs, records event, fire-and-forgets memory extraction (280), then throws `Error("Reached maximum loop iterations.")` — surfaces as an error message in the UI.
- **Confidence:** HIGH

### Q24. What happens at startup if the API key is missing?
- **Answer:** `packages/cli/src/main.ts` → `main` guard → **33–42**
- **⚠️ FLAG (LOW confidence):** The key is **hardcoded inline** (`const apiKey = 'gsk_...'` at main.ts:35), so `if (!apiKey)` can never trigger — this is dead code. It's a great hallucination trap for the eval (a naive RAG might confidently answer "it throws GROQ_API_KEY is not set"), but it is *not* a reachable behavior today. Same pattern in `EpisodicMemoryManager` constructor (Jina key hardcoded at line ~20, with `if (!key) throw`). Verify if you want to keep it; consider rephrasing as "Is there a startup guard for the API key, and does it work?"
- **Confidence:** LOW — flag as intentional trap

---

## Category 5 — Multi-file answers

### Q25. How does a typed message travel from input to a rendered answer?
- **Answer (anchor):** `packages/cli/components/input-bar.tsx` → `InputBar` Enter-submit → **95–113** → then `App.handleSubmit` → `packages/cli/src/index.tsx` → **238–260** → `AgentLoop.execute` → `packages/cli/src/agent/loop.ts` → **15–292** → `GroqClient.chat` → `packages/cli/src/llm-client/groq-client.ts` → **20–59** → rendered by `MessageBubble` → `packages/cli/src/index.tsx` → **125–184**
- **Confidence:** HIGH

### Q26. How is the whole system wired together at boot?
- **Answer (anchor):** `packages/cli/src/main.ts` → `main` → **33–115** (managers → register all 14 tools at **55–68** → ContextBuilder → AgentHarness → GroqClient → AgentLoop → session → UI) + `TerminalUI.start` → `packages/cli/src/terminal.ts` → **11–39** → mounts `App` → `packages/cli/src/index.tsx` → **187–338**
- **Confidence:** HIGH

### Q27. How does the destructive-action confirmation dialog work end-to-end?
- **Answer (anchor):** `packages/cli/src/index.tsx` → `ConfirmDialog` → **57–102** + Y/N/Esc keyboard handler → **204–228** + `buildConfirmHook` → **230–236** ← called by `AgentLoop.execute` gate → `packages/cli/src/agent/loop.ts` → **184–197**
- **Notes:** The hook returns a Promise resolved by the UI; rejected → `User rejected...` result; confirmed → tool executes.
- **Confidence:** HIGH

### Q28. How does the agent remember what it learned across restarts?
- **Answer (anchor):** `packages/cli/src/agent/memory/EpisodicMemoryManager.ts` → `addEpisodicMemory` → **69–86** (appends to `memory/episodic/events.jsonl`) + `SemanticMemoryManager.set` → `packages/cli/src/agent/memory/SemanticMemoryManager.ts` → **37–55** (`memory/semantic.json`) + `ProceduralMemoryManager.addRule` → `packages/cli/src/agent/memory/ProceduralMemoryManager.ts` → **60–70** (`memory/procedural.md`); all driven by `extractMemories` → `memoryClassifier.ts` → **24–83**
- **Confidence:** HIGH

### Q29. Where is tracing configured and how are failures recorded on spans?
- **Answer (anchor):** `packages/cli/src/telemetry.ts` → module-level `tracer` (**6**), `markSpanError` (**13–20**), `NodeSDK` + OTLP exporter (**22–34**) + call sites: `loop.ts` (~60, 281, 313…), `context.ts` (catch blocks), `groq-client.ts` (`callGroq` catch), `agent-harness.ts` (all four traced methods)
- **Confidence:** HIGH

### Q30. How does the slash-command menu open, filter, and get handled?
- **Answer (anchor):** `packages/cli/components/input-bar.tsx` → `handleContentChange` → **35–48** (opens on `/`) + `useCommandMenu` → `packages/cli/components/commands-menu/use-command-menu.ts` → **4–56** + `getFiltererdCommands` → `filter-commands.ts` → **4–7** + render `CommandMenu` → `packages/cli/components/commands-menu/index.tsx` → **16–57** + command definitions `COMMANDS` → `packages/cli/components/commands-menu/commands.tsx` → **3–20**
- **⚠️ FLAG (MEDIUM confidence on "handled"):** Pressing Enter while the menu is open only calls `c.selectAt(c.selectedIndex)` (input-bar.tsx **75–82**) — the `action` on a Command (e.g. `/exit` → `ctx.exit()`) is **never invoked** anywhere I found, and the menu rows' `onExecute` is wired to `selectAt` (input-bar.tsx:145–146). So `/exit` appears to be dead code / a bug. The *open + filter + render* part is solid; the *execute* part is likely broken. Verify.
- **Confidence:** MEDIUM (open/filter/render HIGH; execution LOW)

---

## Flagged items (verify first)

| # | Issue | Risk |
|---|-------|------|
| Q10 | `summarizedUpToMessageId` stored but never used to skip re-summarization; old messages appear re-summarized each compression | Answer still points to right code, but the "how" explanation may be wrong |
| Q12 | `tool_use_failed` retry path depends on Groq's exact error code — never exercised end-to-end here | Retry path may be dead in practice |
| Q18 | main.ts session-creation line range (~96–101) estimated, not grep-verified | Line range may be off by a few |
| Q21 | Catch-block line range (~200–212) estimated from file content | Line range approximate |
| Q24 | API-key guard is dead code (key hardcoded) — LOW confidence as a real behavior | Keep only as an intentional trap |
| Q30 | `/exit` command `action` appears never executed (dead code) — MEDIUM confidence | Answer should probably point at the menu *rendering*, not execution |

## Suggested verification workflow

1. For each HIGH item, spot-check the file → function → line range (they should be exact).
2. For MEDIUM/LOW items, read the flagged code and decide whether to keep, rephrase, or drop.
3. Decide whether the eval should use line ranges at all (they drift on every edit) — consider storing `file + function` as the stable key and treating line ranges as a hint.
4. Convert to your eval format (JSONL/CSV). If useful, ask me to emit a JSONL version after you've corrected the answers.
