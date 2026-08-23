from dataclasses import dataclass


@dataclass
class NovelModel:
    id: int
    title: str
    description: str
    img: str
    language_code: str


@dataclass
class NovelChapterModel:
    id: int
    title: str
    num_chapter: int | None
    content: str
    language_code: str
