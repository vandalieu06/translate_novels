import os
from datetime import datetime

from ollama import chat


class LLMTranslate:
    model: str = os.getenv('OLLAMA_MODEL', 'translategemma:4b')
    prompt: str = """You are a professional English (en) to Spanish (es) translator. Your goal is to accurately convey the meaning and nuances of the original English text while adhering to Spanish grammar, vocabulary, and cultural sensitivities. Produce only the Spanish translation, without any additional explanations or commentary. Please translate the following English text into Spanish:
    """
    max_words: int = 400


class Translate:
    """
    Classe que contienen los metodos de tradducion de novelas
    Connexion con LLM especializada en IA
    """

    name_novel: str

    def __init__(self, name_novel):
        self.name_novel = name_novel

    def split_text_by_words(
        self, paragraphs: list, max_words_per_chunk: int = 400
    ) -> list[str]:
        """
        Divide el texto en fragmentos respetando los párrafos siempre que sea posible,
        asegurando que cada fragmento no supere el máximo de palabras aproximado.
        """
        chunks = []
        current_chunk = []
        current_word_count = 0

        for paragraph in paragraphs:
            paragraph_words = len(paragraph.split())
            # Si un solo párrafo es extremadamente largo, lo manejamos,
            # pero normalmente se agrupan varios párrafos.
            if (
                current_word_count + paragraph_words > max_words_per_chunk
                and current_chunk
            ):
                chunks.append('\n'.join(current_chunk))
                current_chunk = [paragraph]
                current_word_count = paragraph_words
            else:
                current_chunk.append(paragraph)
                current_word_count += paragraph_words

        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        return chunks

    def save_translate(self, translation: str, chapter_title: str):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_chapter_format = chapter_title.split(':')[0].lower().replace(' ', '')
        filename = f'output/{self.name_novel}/{filename_chapter_format}_{timestamp}.md'
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(f'## {chapter_title}\n\n')
            file.write(translation)

        print(f'Chapter saved in {filename}')

    def translate_novel(self, novel: dict):
        chapter_content = novel['content']

        total_words = len(''.join(chapter_content).split())
        print(f'Length novel: {total_words} words')

        # Dividimos el texto en fragmentos
        chunks = self.split_text_by_words(
            chapter_content, max_words_per_chunk=LLMTranslate.max_words
        )
        print(f'Text split into {len(chunks)} chunks.')

        translated_chunks = []

        # Procesamos cada fragmento uno por uno
        for i, chunk in enumerate(chunks, start=1):
            print(
                f'Translating chunk {i}/{len(chunks)}... ({len(chunk.split())} words)'
            )

            response = chat(
                model=LLMTranslate.model,
                messages=[
                    {'role': 'system', 'content': LLMTranslate.prompt},
                    {'role': 'user', 'content': chunk},
                ],
            )

            if response.message.content:
                translated_chunks.append(response.message.content.strip())
            else:
                print(f'Warning: Chunk {i} returned an empty response.')

        # Unimos todas las traducciones con saltos de línea dobles para mantener la estructura
        final_translation = '\n\n'.join(translated_chunks)

        self.save_translate(final_translation, novel['title'])
