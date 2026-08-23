from os import path

# Importamos los modelos nuevos que acabamos de definir en el paso anterior
from novel_cli.core.database.db import (
    Novel,
    NovelChapter,
    NovelChapterTranslation,
    NovelTranslation,
)
from peewee import SqliteDatabase

# 1. Rutas absolutas a los archivos SQLite
OLD_DB_PATH = path.abspath(
    "/home/jhonnyc/Dev/projects/translate_novels/db/backups/novel_backup_18-06-2026.sqlite"
)
NEW_DB_PATH = path.abspath(
    "/home/jhonnyc/Dev/projects/translate_novels/db/novel_v2.sqlite"
)


def migrate_database():
    # Nos conectamos a la base de datos vieja
    old_db = SqliteDatabase(OLD_DB_PATH)
    old_db.connect()

    # Iniciamos un bloque atómico en la nueva base de datos para garantizar la integridad
    new_db = Novel._meta.database
    with new_db.atomic():
        print("Migrando datos de Novelas...")
        # Leemos los datos estructurales y traducibles combinados de la vieja BD
        cursor_novels = old_db.execute_sql(
            "SELECT id, img, title, description FROM novel"
        )

        for row in cursor_novels.fetchall():
            novel_id, img, title, description = row

            # Insertamos la parte estructural en la nueva BD manteniendo el mismo ID original
            Novel.create(id=novel_id, img=img)

            # Insertamos la traducción asociada (usamos 'es' como idioma base por defecto)
            NovelTranslation.create(
                novel_id=novel_id,
                language_code="en",
                title=title if title else "Sin título",
                description=description if description else "",
            )

        print("Migrando datos de Capítulos...")
        # Leemos los capítulos de la vieja BD. Manejamos el caso de que 'len' o 'num_chapter' vengan vacíos
        cursor_chapters = old_db.execute_sql(
            "SELECT id, novel_id, num_chapter, title, content, len FROM novelchapter"
        )

        for row in cursor_chapters.fetchall():
            chap_id, novel_id, num_chapter, title, content, len_code = row

            # Idioma por defecto si la columna 'len' venía vacía
            idioma = "en"
            # Si num_chapter era null, le asignamos un valor por defecto temporal para no romper el índice compuesto
            num_cap = num_chapter if num_chapter is not None else 0

            # Insertamos la parte estructural en la nueva BD manteniendo relaciones e IDs
            NovelChapter.create(id=chap_id, novel_id=novel_id, num_chapter=num_cap)

            # Insertamos el texto traducible en la nueva tabla de traducción de capítulos
            NovelChapterTranslation.create(
                chapter_id=chap_id,
                language_code=idioma,
                title=title if title else f"Capítulo {num_cap}",
                content=content if content else "",
            )

    old_db.close()
    print("\n¡Proceso finalizado con éxito!")
    print(f"Los datos limpios y multidioma están listos en: {NEW_DB_PATH}")
    print(
        "Una vez verifiques que todo está correcto, puedes renombrar este archivo al nombre original."
    )


if __name__ == "__main__":
    migrate_database()
