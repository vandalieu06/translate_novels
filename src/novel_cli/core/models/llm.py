import os
from dataclasses import dataclass


@dataclass
class LLMTranslate:
    model: str = os.getenv("OLLAMA_MODEL", "translategemma:4b")
    prompt: str = """You are a professional English (en) to Spanish (es) translator.
    Your goal is to accurately convey the meaning and nuances of the original English text while adhering to Spanish grammar, vocabulary, and cultural sensitivities.
    Produce only the Spanish translation, without any additional explanations or commentary. Please translate the following English text into Spanish:
    """
    max_words: int = 400
