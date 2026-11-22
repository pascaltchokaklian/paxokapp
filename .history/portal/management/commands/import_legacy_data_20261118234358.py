import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

LEGACY_TABLES = (
    'myapp_country',
    'myapp_region',
    'myapp_col',
    'myapp_col_counter',
    'myapp_col_perform',
    'myapp_activity',
    'myapp_activity_info',
)


class Command(BaseCommand):
    help = 'Copie les tables de la base Cent Cols legacy dans db.sqlite3 (tables vides uniquement).'

    def handle(self, *args, **options):
        legacy_path = Path(settings.CENTCOLS_LEGACY_DB_PATH)
        if not legacy_path.is_file():
            raise CommandError(f'Base legacy introuvable : {legacy_path}')

        source = sqlite3.connect(f'{legacy_path.as_uri()}?mode=ro', uri=True)
        target = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            for table in LEGACY_TABLES:
                ddl = source.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
                if ddl is None:
                    self.stdout.write(f'{table} : absente de la base legacy')
                    continue
                target.execute(ddl[0].replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS', 1))
                if target.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]:
                    self.stdout.write(f'{table} : déjà rempli, ignoré')
                    continue
                rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
                if rows:
                    placeholders = ', '.join('?' * len(rows[0]))
                    target.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
                self.stdout.write(f'{table} : {len(rows)} lignes copiées')
            target.commit()
        finally:
            source.close()
            target.close()
