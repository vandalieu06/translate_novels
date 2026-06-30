from os import path

from peewee import *
from playhouse.migrate import *

db = SqliteDatabase(
    path.abspath('D:/developer/projects/translate-novels/db/novel_cli.db')
)
migrator = SqliteMigrator(db)
new_field = TextField(default='es')

with db.atomic():
    migrate(migrator.add_column('novelchapter', 'len', new_field))

print('Migración completada con éxito.')
