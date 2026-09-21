import requests
from django.core.management.base import BaseCommand

from myapp.models import Segment, Strava_user


class Command(BaseCommand):
    help = "Synchronise activity_type des segments depuis le premier effort Strava."

    def handle(self, *args, **options):
        strava_user = (
            Strava_user.objects.exclude(access_token__in=("", "-", "notFound"))
            .exclude(access_token__isnull=True)
            .first()
        )
        if not strava_user:
            self.stderr.write(
                self.style.ERROR("Aucun utilisateur Strava avec un token disponible.")
            )
            return

        segments = Segment.objects.exclude(strava_segment_id__isnull=True)
        updated_count = 0
        unchanged_count = 0
        skipped_count = 0

        headers = {"Authorization": f"Bearer {strava_user.access_token}"}
        for segment in segments.iterator():
            try:
                response = requests.get(
                    "https://www.strava.com/api/v3/segment_efforts",
                    headers=headers,
                    params={"segment_id": segment.strava_segment_id, "per_page": 1},
                    timeout=15,
                )
                response.raise_for_status()
                efforts = response.json()
            except (requests.RequestException, ValueError) as error:
                skipped_count += 1
                self.stderr.write(
                    f"Segment {segment.strava_segment_id}: erreur Strava: {error}"
                )
                continue

            if not isinstance(efforts, list) or not efforts:
                skipped_count += 1
                self.stderr.write(
                    f"Segment {segment.strava_segment_id}: aucun effort Strava."
                )
                continue

            activity_type = efforts[0].get("activity_type")
            if not isinstance(activity_type, str) or not activity_type:
                skipped_count += 1
                self.stderr.write(
                    f"Segment {segment.strava_segment_id}: activity_type absent."
                )
                continue

            if segment.activity_type == activity_type:
                unchanged_count += 1
                continue

            segment.activity_type = activity_type
            segment.save(update_fields=["activity_type"])
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{updated_count} mis a jour, {unchanged_count} deja correct(s), "
                f"{skipped_count} non traite(s)."
            )
        )
