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

    def _import_performances(self, source):
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {'myapp_perform', 'myapp_segment', 'myapp_activity'} <= tables:
            return

        # Les performances legacy n'ont pas d'activite : rattachement par jour, comme l'ancienne appli
        activities = {}
        for user_id, strava_id, start in source.execute(
            'SELECT strava_user_id, strava_id, act_start_date FROM myapp_activity ORDER BY act_start_date'
        ):
            start_date = _parse_utc(start)
            if start_date is not None:
                activities.setdefault((user_id, start_date.date()), []).append((start_date, strava_id))

        efforts = []
        skipped = 0
        rows = source.execute(
            'SELECT p.strava_perf_id, p.strava_user_id, p.perf_date, p.perf_chrono, p.perf_vam, '
            's.strava_segment_id, s.segment_name '
            'FROM myapp_perform p JOIN myapp_segment s ON s.segment_id = p.segment_id '
            'WHERE p.strava_perf_id IS NOT NULL AND s.strava_segment_id IS NOT NULL'
        ).fetchall()
        for effort_id, user_id, perf_date, chrono, vam, segment_id, segment_name in rows:
            start_date = _parse_utc(perf_date)
            candidates = activities.get((user_id, start_date.date())) if start_date else None
            if not candidates:
                skipped += 1
                continue
            earlier = [item for item in candidates if item[0] <= start_date]
            activity_id = (earlier[-1] if earlier else candidates[0])[1]
            efforts.append(SegmentEffort(
                effort_id=effort_id,
                strava_user_id=user_id,
                strava_activity_id=activity_id,
                segment_id=segment_id,
                segment_name=segment_name,
                start_date=start_date,
                elapsed_time=chrono,
                vam=vam,
            ))
        SegmentEffort.objects.bulk_create(efforts, ignore_conflicts=True, batch_size=500)
        self.stdout.write(f'segments : {len(efforts)} performances importées, {skipped} sans activité')


def _parse_utc(value):
    parsed = parse_datetime(str(value).replace(' ', 'T')) if value else None
    if parsed is None:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
