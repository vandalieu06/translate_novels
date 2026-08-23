import re

from novel_cli.database.db import NovelChapter

chapters = NovelChapter.select(NovelChapter.id, NovelChapter.title).where(
    NovelChapter.novel == 1
)
modified_chapters = []

for c in chapters:
    if c.title != "" and (match := re.search(r"Chapter\s+(\d+)", c.title)):
        c.num_chapter = int(match.group(1))
        modified_chapters.append(c)

with NovelChapter._meta.database.atomic():
    NovelChapter.bulk_update(
        modified_chapters, fields=[NovelChapter.num_chapter], batch_size=50
    )
