from peewee import DoesNotExist

from novel_cli.core.database import (
    Novel,
    NovelChapter,
    NovelChapterTranslation,
    NovelTranslation,
)
from novel_cli.core.models import NovelChapterModel, NovelModel


class RepostoryNovel:
    def save(self, novel: NovelModel) -> Novel:
        db = Novel._meta.database
        with db.atomic():
            novel_base = Novel.create(img=novel.img)
            NovelTranslation.create(
                novel=novel_base,
                title=novel.title,
                language_code=novel.language_code,
                description=novel.description,
            )
            return novel_base

    def get_all(self, language_code: str = "en") -> list[NovelModel]:
        translations = (
            NovelTranslation.select(NovelTranslation, Novel)
            .join(Novel)
            .where((NovelTranslation.language_code == language_code))
        )

        novels: list[NovelModel] = []

        for n in translations:
            novel = NovelModel(
                id=n.id,
                title=n.title,
                description=n.description,
                img=n.novel.img,
                language_code=n.language_code,
            )
            novels.append(novel)

        return novels

    def get_by_id(self, id: int, language_code: str = "en") -> NovelModel | None:
        try:
            translation = (
                NovelTranslation.select(NovelTranslation, Novel)
                .join(Novel)
                .where(
                    (Novel.id == id) & (NovelTranslation.language_code == language_code)
                )
                .get()
            )

            return NovelModel(
                id=translation.id,
                title=translation.title,
                description=translation.description,
                img=translation.novel.img,
                language_code=translation.language_code,
            )
        except DoesNotExist:
            return None

    def get_by_title(self, title: str) -> NovelModel | None:
        try:
            translation = (
                NovelTranslation.select(NovelTranslation, Novel)
                .join(Novel)
                .where((NovelTranslation.title == title))
                .get()
            )

            return NovelModel(
                id=translation.id,
                title=translation.title,
                description=translation.description,
                img=translation.novel.img,
                language_code=translation.language_code,
            )
        except DoesNotExist:
            return None


class RepostoryNovelChapter:
    def save(self, novel_id: int, chapter: NovelChapterModel) -> NovelChapter:
        db = NovelChapter._meta.database
        with db.atomic():
            chapter_base = NovelChapter.create(
                novel_id=novel_id,
                num_chapter=chapter.num_chapter,
            )

            NovelChapterTranslation.create(
                chapter=chapter_base,
                title=chapter.title,
                content=chapter.content,
                language_code=chapter.language_code,
            )
            return chapter_base

    def get_by_id(self, id: int, language_code: str = "en") -> NovelChapterModel | None:
        try:
            translation = (
                NovelChapterTranslation.select(NovelChapterTranslation, NovelChapter)
                .join(NovelChapter)
                .where(
                    (NovelChapter.id == id)
                    & (NovelChapterTranslation.language_code == language_code)
                )
                .get()
            )

            return NovelChapterModel(
                id=translation.id,
                title=translation.title,
                num_chapter=translation.chapter.num_chapter,
                content=translation.content,
                language_code=translation.language_code,
            )
        except DoesNotExist:
            return None

    def get_all(
        self, novel_id: int, language_code: str = "en"
    ) -> list[NovelChapterModel]:
        translations = (
            NovelChapterTranslation.select(NovelChapterTranslation, NovelChapter)
            .join(NovelChapter)
            .where(
                (NovelChapter.novel == novel_id)
                & (NovelChapterTranslation.language_code == language_code)
            )
            .order_by(NovelChapter.num_chapter)
        )

        chapters: list[NovelChapterModel] = []

        for t in translations:
            chapter = NovelChapterModel(
                id=t.id,
                title=t.title,
                num_chapter=t.chapter.num_chapter,
                content=t.content,
                language_code=t.language_code,
            )
            chapters.append(chapter)

        return chapters
