"""
prompt_builder.py — pure formatting, no API calls, no retrieval logic here.
Takes retrieved chunks + a question, returns a single prompt string ready for the generator.
"""

from app.retriever import RetrievedChunk


SYSTEM_INSTRUCTIONS = """You are a code assistant answering questions about a codebase.

Rules you MUST follow:
1. Answer ONLY using the information in the provided code context below. Do not use outside knowledge.
2. If the context does not contain enough information to answer confidently, say so explicitly —
   do not guess or make up an answer.
3. Every claim you make must be grounded in one of the provided chunks. Cite the source for each
   claim using the format (file_path:start_line-end_line).
4. Be concise and technical. This is for a developer, not a general audience.
"""


def build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks + question into a single prompt string."""

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

    prompt = f"""{SYSTEM_INSTRUCTIONS}

--- CODE CONTEXT ---
{context_block}
--- END CODE CONTEXT ---

Question: {question}

Answer (remember to cite file_path:start_line-end_line for every claim):"""

    return prompt

