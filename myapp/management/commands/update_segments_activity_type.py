from django.core.management.base import BaseCommand

from myapp.models import Segment


class Command(BaseCommand):
    help = 'Met activity_type a "riding" pour tous les segments existants.'

    def handle(self, *args, **options):
        updated_count = Segment.objects.exclude(activity_type="riding").update(
            activity_type="riding"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{updated_count} segment(s) mis a jour avec "
                'activity_type="riding".'
            )
        )
