from django.core.management.base import BaseCommand

from myapp.models import Segment


class Command(BaseCommand):
    help = 'Supprime les segments dont activity_type est different de "riding".'

    def handle(self, *args, **options):
        segments = Segment.objects.exclude(activity_type="riding")
        deleted_count, _ = segments.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"{deleted_count} segment(s) supprime(s); seuls les segments "
                'activity_type="riding" sont conserves.'
            )
        )
