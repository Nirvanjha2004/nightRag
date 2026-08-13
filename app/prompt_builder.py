"""
prompt_builder.py — pure formatting, no API calls, no retrieval logic here.
Returns (system_prompt, user_prompt) so the generator can send them as
separate roles — chat-tuned models generally weight `system` instructions
more heavily than instructions buried inside a `user` message.
"""

from app.retriever import RetrievedChunk


SYSTEM_INSTRUCTIONS = """You are a code assistant answering questions about a codebase.

Rules you MUST follow:
1. Answer ONLY using the information in the provided code context below. Do not use outside knowledge.
2. IMPORTANT: You may recognize this codebase or library from your training data. IGNORE what you
   remember about it. Even if you are confident you know the answer from memory, you must verify
   it appears in the provided context — if it doesn't appear there, treat it as unknown.
3. If the context does not contain enough information to answer confidently, say so explicitly —
   do not guess or fill gaps using prior knowledge.
4. Every claim you make must be grounded in one of the provided chunks. Cite the source for each
   claim using the format (file_path:start_line-end_line).
5. Be concise and technical. This is for a developer, not a general audience.
"""

# Short reminder repeated right before the answer — instructions placed far
# from the generation point (behind a wall of context chunks) get less
# weight than ones placed close to it. This is a deliberate repeat, not
# redundant copy-paste.
FINAL_REMINDER = (
    "Reminder: use ONLY the context above, ignore anything you recall about this "
    "library from training, and say so explicitly if the context is insufficient."
)


def build_prompt(question: str, chunks: list[RetrievedChunk]) -> tuple[str, str]:
    """Format retrieved chunks + question into (system_prompt, user_prompt)."""

    if not chunks:
        context_block = "No relevant code context was found for this question."
    else:
        context_parts = []
        for i, c in enumerate(chunks, start=1):
            context_parts.append(
                f"[Chunk {i}] {c.file_path}:{c.start_line}-{c.end_line} "
                f"({c.node_type}: {c.name})\n"
                f"```\n{c.text}\n```"
            )
        context_block = "\n\n".join(context_parts)

    user_prompt = f"""--- CODE CONTEXT ---
{context_block}
--- END CODE CONTEXT ---

Question: {question}

{FINAL_REMINDER}

Answer (remember to cite file_path:start_line-end_line for every claim):"""

    return SYSTEM_INSTRUCTIONS, user_prompt