from os import path

from peewee import *
from playhouse.migrate import *

db_path = path.abspath("/home/jhonnyc/Dev/projects/translate_novels/db/novel.sqlite")

db = SqliteDatabase(db_path)
migrator = SqliteMigrator(db)

with db.atomic():
    print("Configurando Claves Foráneas e Índices de producción...")

    # 1. Añadir restricciones de Foreign Key reales usando el migrator
    # Esto vincula lógicamente noveltranslation -> novel y novelchaptertranslation -> novelchapter
    migrate(
        migrator.add_foreign_key_constraint(
            "noveltranslation", "novel_id", "novel", "id", on_delete="CASCADE"
        ),
        migrator.add_foreign_key_constraint(
            "novelchaptertranslation",
            "chapter_id",
            "novelchapter",
            "id",
            on_delete="CASCADE",
        ),
    )
    print("✓ Claves foráneas añadidas con éxito (ON DELETE CASCADE).")

    # 2. Añadir los índices compuestos únicos para el entorno multidioma
    # Esto garantiza que no haya más de una traducción en el mismo idioma para un mismo elemento
    migrate(
        migrator.add_index(
            "noveltranslation", ["novel_id", "language_code"], unique=True
        ),
        migrator.add_index(
            "novelchaptertranslation", ["chapter_id", "language_code"], unique=True
        ),
        migrator.add_index("novelchapter", ["novel_id", "num_chapter"], unique=True),
    )
    print("✓ Índices compuestos únicos de idioma y capítulos creados.")
    print("¡Base de datos optimizada al 100%!")
