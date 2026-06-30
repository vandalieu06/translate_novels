import datetime
from os import path

from peewee import CharField, ForeignKeyField, Model, SqliteDatabase, TextField

db = SqliteDatabase(
    path.abspath('D:/developer/projects/translate-novels/db/novel_cli.db')
)


class BaseModel(Model):
    class Meta:
        database = db


class Novel(BaseModel):
    title = CharField()
    description = TextField()
    img = CharField(unique=True)


class NovelChapter(BaseModel):
    novel = ForeignKeyField(Novel, backref='chapters')
    title = CharField(unique=True)
    content = TextField()
    len = TextField(default='es')


db.connect()
db.create_tables([Novel, NovelChapter])
