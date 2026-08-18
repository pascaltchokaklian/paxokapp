from django.core.management.base import BaseCommand
import openpyxl
from myapp.models import Col


class Command(BaseCommand):
    help = "Importe les cols corses depuis un fichier Excel"

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Chemin vers le fichier Excel'
        )

    def handle(self, *args, **options):
        file_path = options['file_path']
        
        try:
            # Charger le fichier Excel
            wb = openpyxl.load_workbook(file_path)
            ws = wb.active
            
            rows = list(ws.iter_rows(values_only=True))
            
            # Ignorer l'en-tête (première ligne)
            cols_data = rows[1:]
            
            created_count = 0
            updated_count = 0
            skipped_count = 0
            
            for row in cols_data:
                if not row[0]:  # Ignorer les lignes vides
                    continue
                
                col_code, col_name, col_alt, col_lon, col_lat, col_type = row
                
                # Vérifier que les données essentielles existent
                if not col_code or not col_name:
                    self.stdout.write(f'⚠️  Ligne ignorée (données manquantes): {row}')
                    skipped_count += 1
                    continue
                
                try:
                    # Vérifier si le col existe déjà
                    col_obj, created = Col.objects.update_or_create(
                        col_code=col_code,
                        defaults={
                            'col_name': col_name,
                            'col_alt': col_alt,
                            'col_lon': col_lon,
                            'col_lat': col_lat,
                            'col_type': col_type,
                        }
                    )
                    
                    if created:
                        created_count += 1
                        self.stdout.write(f'✅ Créé: {col_code} - {col_name}')
                    else:
                        updated_count += 1
                        self.stdout.write(f'🔄 Mis à jour: {col_code} - {col_name}')
                
                except Exception as e:
                    self.stdout.write(f'❌ Erreur pour {col_code}: {str(e)}')
                    skipped_count += 1
            
            # Résumé
            self.stdout.write(self.style.SUCCESS(f'\n📊 Importation terminée!'))
            self.stdout.write(f'  ✅ Créés: {created_count}')
            self.stdout.write(f'  🔄 Mis à jour: {updated_count}')
            self.stdout.write(f'  ⚠️  Ignorés: {skipped_count}')
            self.stdout.write(f'  📈 Total traité: {created_count + updated_count}')
        
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Fichier non trouvé: {file_path}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erreur: {str(e)}'))
