from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Document, DocumentType

User = get_user_model()


class ArchiveTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "admin1", password="pw-for-tests-123", role=User.Role.ADMIN
        )
        self.staff = User.objects.create_user(
            "staff1", password="pw-for-tests-123", role=User.Role.USER
        )

    def make(self, doc_type=DocumentType.MEMORANDUM, **kwargs):
        return Document.objects.create(
            doc_type=doc_type,
            series_year=kwargs.pop("series_year", 2026),
            subject=kwargs.pop("subject", "Test subject"),
            date_issued=date(2026, 1, 15),
            created_by=self.admin,
            **kwargs,
        )


class ControlNumberTests(ArchiveTestCase):
    def test_numbers_increment_per_type_and_year(self):
        a = self.make()
        b = self.make()
        c = self.make(doc_type=DocumentType.OFFICE_ORDER)
        d = self.make(series_year=2025)
        self.assertEqual((a.number, b.number), (1, 2))
        self.assertEqual(c.number, 1)
        self.assertEqual(d.number, 1)

    def test_control_number_format(self):
        doc = self.make()
        self.assertEqual(doc.control_number, "MEMORANDUM No. 001, s. 2026")

    def test_indorsement_prefix(self):
        doc = self.make(doc_type=DocumentType.INDORSEMENT, indorsement_level=2)
        self.assertEqual(doc.control_number, "2nd INDORSEMENT No. 001, s. 2026")


class AccessControlTests(ArchiveTestCase):
    def test_anonymous_is_sent_to_sign_in(self):
        response = self.client.get(reverse("documents:document_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_staff_user_can_search_but_not_file(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("documents:document_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("documents:document_create")).status_code, 403)

    def test_staff_user_cannot_reach_admin_pages(self):
        self.client.force_login(self.staff)
        for name in ["documents:audit_trail", "documents:recycle_bin", "accounts:user_list"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_admin_can_file(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("documents:document_create")).status_code, 200)

    def test_confidential_records_are_hidden_from_staff(self):
        secret = self.make(classification=Document.Classification.CONFIDENTIAL)
        self.client.force_login(self.staff)
        response = self.client.get(secret.get_absolute_url())
        self.assertEqual(response.status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(secret.get_absolute_url()).status_code, 200)


class SearchTests(ArchiveTestCase):
    def test_keyword_and_type_filters(self):
        self.make(subject="Travel order guidelines")
        self.make(doc_type=DocumentType.EXECUTIVE_ORDER, subject="Budget realignment")
        self.client.force_login(self.staff)

        hits = self.client.get(reverse("documents:document_list"), {"q": "travel"})
        self.assertEqual(len(hits.context["documents"]), 1)

        hits = self.client.get(reverse("documents:document_list"), {"doc_type": "EO"})
        self.assertEqual(len(hits.context["documents"]), 1)


class SoftDeleteTests(ArchiveTestCase):
    def test_removed_record_leaves_search_but_keeps_its_number(self):
        doc = self.make()
        doc.soft_delete()
        self.assertFalse(Document.objects.visible_to(self.staff).filter(pk=doc.pk).exists())
        replacement = self.make(subject="Next one")
        self.assertEqual(replacement.number, 2)
