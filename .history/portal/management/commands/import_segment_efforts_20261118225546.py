import requests
from django.core.management.base import BaseCommand
from social_django.models import UserSocialAuth

from ...strava_sync import ACTIVITIES_URL, _access_token, import_segment_efforts


class Command(BaseCommand):
    help = 'Importe les segments Strava de toutes les activites existantes.'

    def handle(self, *args, **options):
        for social_auth in UserSocialAuth.objects.filter(provider='strava'):
            strava_user_id = int(social_auth.uid)
            headers = {'Authorization': f'Bearer {_access_token(social_auth)}'}
            page = 1
            count = 0
            while True:
                response = requests.get(
                    ACTIVITIES_URL,
                    headers=headers,
                    params={'per_page': 200, 'page': page},
                    timeout=15,
                )
                response.raise_for_status()
                activities = response.json()
                if not activities:
                    break
                for activity in activities:
                    import_segment_efforts(strava_user_id, int(activity['id']), headers)
                    count += 1
                page += 1
            self.stdout.write(f'{strava_user_id} : {count} activites traitees')
