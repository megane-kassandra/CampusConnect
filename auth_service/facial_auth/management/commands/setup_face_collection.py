from django.core.management.base import BaseCommand

from facial_auth.rekognition import ensure_collection


class Command(BaseCommand):
    help = "Crée la collection AWS Rekognition utilisée par l'authentification faciale."

    def handle(self, *args, **options):
        ensure_collection()
        self.stdout.write(self.style.SUCCESS("Collection Rekognition prête."))
