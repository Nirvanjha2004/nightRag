"""
generator.py — pure LLM call wrapper. No prompt-building logic, no retrieval logic here.
Takes a finished prompt string, returns the generated answer text.
"""

from groq import Groq


class Generator:
    def __init__(self, api_key: str, model: str = "openai/gpt-oss-120b"):
        self.client = Groq(api_key=api_key)
        self.model = model

    def generate(self, prompt: str, temperature: float = 0.1, max_tokens: int = 1024) -> str:
        """Send the prompt to Groq and return the generated answer text.

        temperature is kept low (0.1) by default since this is a factual,
        context-grounded RAG answer, not creative generation — reduces the
        chance of the model drifting from the provided context.
        """

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content