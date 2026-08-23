from os import path

from peewee import *
from playhouse.migrate import *

db = SqliteDatabase(
    path.abspath("/home/jhonny/dev/projects/translate_novels/db/novel.sqlite")
)
migrator = SqliteMigrator(db)
num_chapter = IntegerField(unique=True, null=True)

with db.atomic():
    migrate(migrator.add_column("novelchapter", "num_chapter", num_chapter))

print("Migración completada con éxito.")
