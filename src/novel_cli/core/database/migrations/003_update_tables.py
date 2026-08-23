from os import path

from peewee import *
from playhouse.migrate import *

# Configura tu ruta correspondiente según el sistema operativo
db_path = path.abspath("/home/jhonnyc/Dev/projects/translate_novels/db/novel.sqlite")
db = SqliteDatabase(db_path)
migrator = SqliteMigrator(db)


# 1. Definimos las nuevas estructuras de traducción para la migración
class NovelTranslation(Model):
    id = AutoField()
    novel_id = IntegerField()  # Relación simple para el traspaso de datos
    language_code = CharField(max_length=5)
    title = CharField()
    description = TextField()

    class Meta:
        database = db
        table_name = "noveltranslation"


class NovelChapterTranslation(Model):
    id = AutoField()
    chapter_id = IntegerField()
    language_code = CharField(max_length=5)
    title = CharField()
    content = TextField()

    class Meta:
        database = db
        table_name = "novelchaptertranslation"


# Iniciamos el bloque atómico global
with db.atomic():
    print("Iniciando migración estructural y de datos...")

    # --- PASO 1: Crear las nuevas tablas de traducción ---
    db.create_tables([NovelTranslation, NovelChapterTranslation], safe=True)

    # --- PASO 2: Migrar datos de Novelas ---
    # Asumimos que tus datos actuales están en un idioma base, por ejemplo 'es' o 'en'
    # Usamos consultas crudas (execute_sql) para evitar conflictos con los modelos cambiados
    cursor = db.execute_sql("SELECT id, title, description FROM novel")
    for row in cursor.fetchall():
        novel_id, title, description = row
        NovelTranslation.create(
            novel_id=novel_id,
            language_code="en",  # Ajusta al idioma actual de tus datos
            title=title,
            description=description,
        )
    print("Datos de novelas migrados a la tabla de traducción.")

    # --- PASO 3: Migrar datos de Capítulos ---
    cursor = db.execute_sql("SELECT id, title, content, len FROM novelchapter")
    for row in cursor.fetchall():
        chapter_id, title, content, idioma_origen = row
        # Si 'len' venía vacío o nulo, le asignamos un valor por defecto
        idioma = idioma_origen if idioma_origen else "en"

        NovelChapterTranslation.create(
            chapter_id=chapter_id, language_code=idioma, title=title, content=content
        )
    print("Datos de capítulos migrados a la tabla de traducción.")

    # 4. PASO CLAVE: Eliminar los índices problemáticos antiguos antes de modificar columnas
    print("Eliminando índices antiguos redundantes...")
    db.execute_sql("DROP INDEX IF EXISTS novelchapter_title")
    db.execute_sql("DROP INDEX IF EXISTS novelchapter_num_chapter")

    # --- PASO 6: Limpiar columnas obsoletas de las tablas originales ---
    # Como SQLite no soporta DROP COLUMN de forma óptima en versiones antiguas
    # y para limpiar los índices "unique" viejos, usamos el migrator de Peewee:

    # Eliminar campos traducibles de la tabla Novel
    # Eliminar campos traducibles de la tabla NovelChapter
    migrate(
        migrator.drop_column("novel", "title"),
        migrator.drop_column("novel", "description"),
        migrator.drop_column("novelchapter", "title"),
        migrator.drop_column("novelchapter", "content"),
        migrator.drop_column("novelchapter", "len"),
    )

    print("Columnas antiguas eliminadas con éxito.")
    print("¡Migración multimidioma completada de forma atómica!")
