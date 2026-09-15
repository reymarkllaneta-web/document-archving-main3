"""Create a demo administrator, a staff user and a few sample records.

    python manage.py seed_archive
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from documents.models import Document, DocumentType

User = get_user_model()

SAMPLES = [
    (DocumentType.MEMORANDUM, "Guidelines on the submission of year-end accomplishment reports",
     "Office of the Administrator", "Atty. R. Salazar", None),
    (DocumentType.MEMORANDUM, "Adjusted office hours during the local holiday",
     "Human Resource Division", "Atty. R. Salazar", None),
    (DocumentType.OFFICE_ORDER, "Designation of officers-in-charge for the third quarter",
     "Office of the Administrator", "Atty. R. Salazar", None),
    (DocumentType.EXECUTIVE_ORDER, "Creating the records digitization task force",
     "Office of the Municipal Mayor", "Hon. C. Villanueva", None),
    (DocumentType.INDORSEMENT, "Respectfully forwarded to the Budget Office for comment",
     "Office of the Administrator", "Atty. R. Salazar", 1),
]


class Command(BaseCommand):
    help = "Seed the archive with demo accounts and sample documents."

    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "first_name": "Rosa", "last_name": "Salazar",
                "email": "admin@carigara.gov.ph", "role": User.Role.ADMIN,
                "office": "Records Section", "position": "Records Officer IV",
                "is_staff": True, "is_superuser": True,
            },
        )
        if created:
            admin.set_password("archive-admin-2026")
            admin.save()
            self.stdout.write(self.style.SUCCESS("Administrator 'admin' created."))

        staff, created = User.objects.get_or_create(
            username="clerk",
            defaults={
                "first_name": "Mario", "last_name": "Reyes",
                "email": "clerk@carigara.gov.ph", "role": User.Role.USER,
                "office": "Budget Office", "position": "Administrative Aide VI",
            },
        )
        if created:
            staff.set_password("archive-user-2026")
            staff.save()
            self.stdout.write(self.style.SUCCESS("Staff user 'clerk' created."))

        year = date.today().year
        made = 0
        for offset, (doc_type, subject, office, signatory, level) in enumerate(SAMPLES):
            if Document.objects.filter(subject=subject).exists():
                continue
            Document.objects.create(
                doc_type=doc_type,
                series_year=year,
                subject=subject,
                description="Sample record created by seed_archive.",
                date_issued=date.today() - timedelta(days=offset * 9),
                originating_office=office,
                signatory=signatory,
                indorsement_level=level,
                keywords="sample, demo",
                created_by=admin,
                updated_by=admin,
            )
            made += 1

        self.stdout.write(self.style.SUCCESS(f"{made} sample document(s) filed."))
        self.stdout.write("Sign in as admin / archive-admin-2026 or clerk / archive-user-2026.")
        self.stdout.write(self.style.WARNING("Change both passwords before any real use."))
