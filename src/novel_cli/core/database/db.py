from pathlib import Path

from peewee import (
    AutoField,
    CharField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

db_url = Path("/home/jhonnyc/Dev/projects/translate_novels/db/novel_v2.sqlite")
db = SqliteDatabase(str(db_url.resolve()))


class BaseModel(Model):
    class Meta:
        database = db


class Novel(BaseModel):
    id = AutoField()
    img = CharField(unique=True)


class NovelTranslation(BaseModel):
    id = AutoField()
    novel = ForeignKeyField(Novel, backref="translations", on_delete="CASCADE")
    language_code = CharField(max_length=5)
    title = CharField()
    description = TextField()

    class Meta:
        indexes = ((("novel", "language_code"), True),)


class NovelChapter(BaseModel):
    id = AutoField()
    novel = ForeignKeyField(Novel, backref="chapters", on_delete="CASCADE")
    num_chapter = IntegerField(null=True)

    class Meta:
        indexes = ((("novel", "num_chapter"), True),)


class NovelChapterTranslation(BaseModel):
    id = AutoField()
    chapter = ForeignKeyField(NovelChapter, on_delete="CASCADE")
    language_code = CharField(max_length=5)
    title = CharField(unique=True)
    content = TextField()

    class Meta:
        indexes = ((("chapter", "language_code"), True),)


db.connect()
db.create_tables([Novel, NovelTranslation, NovelChapter, NovelChapterTranslation])
