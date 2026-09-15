import os
import uuid
from datetime import date

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone


def archive_upload_path(instance, filename):
    """media/archive/<year>/<type>/<uuid>.<ext> — keeps originals from colliding."""
    ext = os.path.splitext(filename)[1].lower()
    return f"archive/{instance.series_year}/{instance.doc_type}/{uuid.uuid4().hex}{ext}"


def attachment_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"attachments/{instance.document.series_year}/{uuid.uuid4().hex}{ext}"


def import_upload_path(instance, filename):
    return f"imports/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.csv"


def scan_stage_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"scan-staging/{instance.batch_id}/{uuid.uuid4().hex}{ext}"


class DocumentType(models.TextChoices):
    MEMORANDUM = "MEMO", "Memorandum"
    INDORSEMENT = "IND", "Indorsement"
    OFFICE_ORDER = "OO", "Office Order"
    EXECUTIVE_ORDER = "EO", "Executive Order"


# Long form used on the printed control number, e.g. "MEMORANDUM No. 012, s. 2026"
TYPE_LONG_NAME = {
    DocumentType.MEMORANDUM: "MEMORANDUM",
    DocumentType.INDORSEMENT: "INDORSEMENT",
    DocumentType.OFFICE_ORDER: "OFFICE ORDER",
    DocumentType.EXECUTIVE_ORDER: "EXECUTIVE ORDER",
}


class DocumentQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Staff users never see confidential records or soft-deleted ones."""
        qs = self.filter(is_deleted=False)
        if user.is_archive_admin:
            return qs
        return qs.exclude(classification=Document.Classification.CONFIDENTIAL)

    def search(self, term):
        if not term:
            return self
        return self.filter(
            models.Q(subject__icontains=term)
            | models.Q(description__icontains=term)
            | models.Q(keywords__icontains=term)
            | models.Q(originating_office__icontains=term)
            | models.Q(signatory__icontains=term)
            | models.Q(addressee__icontains=term)
        )


class Document(models.Model):
    """One archived record: a Memorandum, Indorsement, Office Order or Executive Order."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "In effect"
        SUPERSEDED = "SUPERSEDED", "Superseded"
        REVOKED = "REVOKED", "Revoked"
        ARCHIVED = "ARCHIVED", "Closed and archived"

    class Classification(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        INTERNAL = "INTERNAL", "Internal"
        CONFIDENTIAL = "CONFIDENTIAL", "Confidential"

    doc_type = models.CharField("Document type", max_length=8, choices=DocumentType.choices)
    series_year = models.PositiveIntegerField("Series year", default=date.today().year)
    number = models.PositiveIntegerField(
        "Number", blank=True, null=True,
        help_text="Leave blank to take the next number in this series.",
    )

    subject = models.CharField(max_length=255)
    description = models.TextField("Summary or full text", blank=True)
    date_issued = models.DateField(default=date.today)
    effectivity_date = models.DateField(blank=True, null=True)

    originating_office = models.CharField(max_length=150, blank=True)
    signatory = models.CharField("Signed by", max_length=150, blank=True)
    addressee = models.CharField("Addressed to", max_length=255, blank=True)
    keywords = models.CharField(
        max_length=255, blank=True, help_text="Comma-separated tags used by search."
    )

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    classification = models.CharField(
        max_length=12, choices=Classification.choices, default=Classification.INTERNAL
    )

    file = models.FileField("Scanned copy", upload_to=archive_upload_path, blank=True, null=True)
    page_count = models.PositiveIntegerField(blank=True, null=True)
    physical_location = models.CharField(
        "Physical file location", max_length=150, blank=True,
        help_text="Where the hard copy sits, e.g. Cabinet 3, Drawer B.",
    )

    # An indorsement usually forwards an earlier document; a superseding order
    # points back at what it replaced. Both use this link.
    related_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="referenced_by", verbose_name="Refers to document",
    )
    indorsement_level = models.PositiveSmallIntegerField(
        blank=True, null=True,
        help_text="1 for 1st Indorsement, 2 for 2nd, and so on.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documents_created"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True,
        related_name="documents_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        ordering = ["-series_year", "doc_type", "-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["doc_type", "series_year", "number"],
                name="unique_control_number",
            )
        ]
        indexes = [
            models.Index(fields=["doc_type", "series_year"]),
            models.Index(fields=["date_issued"]),
            models.Index(fields=["subject"]),
        ]

    def __str__(self):
        return f"{self.control_number} — {self.subject}"

    def get_absolute_url(self):
        return reverse("documents:document_detail", args=[self.pk])

    # -- control number -------------------------------------------------
    @property
    def control_number(self) -> str:
        """e.g. 'MEMORANDUM No. 012, s. 2026' or '2nd INDORSEMENT No. 004, s. 2026'."""
        long_name = TYPE_LONG_NAME.get(self.doc_type, self.get_doc_type_display().upper())
        prefix = ""
        if self.doc_type == DocumentType.INDORSEMENT and self.indorsement_level:
            prefix = f"{ordinal(self.indorsement_level)} "
        number = f"{self.number:03d}" if self.number else "—"
        return f"{prefix}{long_name} No. {number}, s. {self.series_year}"

    @property
    def short_number(self) -> str:
        return f"{self.doc_type}-{self.number:03d}-{self.series_year}" if self.number else "unassigned"

    @classmethod
    def next_number(cls, doc_type, series_year) -> int:
        last = (
            cls.objects.filter(doc_type=doc_type, series_year=series_year)
            .aggregate(models.Max("number"))["number__max"]
        )
        return (last or 0) + 1

    def save(self, *args, **kwargs):
        if self.number is None:
            with transaction.atomic():
                # Lock the series so two clerks saving at once can't take the
                # same number.
                locked = Document.objects.select_for_update().filter(
                    doc_type=self.doc_type, series_year=self.series_year
                )
                last = locked.aggregate(models.Max("number"))["number__max"]
                self.number = (last or 0) + 1
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])

    @property
    def keyword_list(self):
        return [k.strip() for k in self.keywords.split(",") if k.strip()]

    @property
    def file_extension(self):
        return os.path.splitext(self.file.name)[1].lstrip(".").upper() if self.file else ""


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


class Attachment(models.Model):
    """Enclosures filed with the main document."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="attachments")
    label = models.CharField(max_length=150)
    file = models.FileField(upload_to=attachment_upload_path)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.label


class AccessLog(models.Model):
    """Immutable trail of who touched what. Administrators can read it; nobody edits it."""

    class Action(models.TextChoices):
        LOGIN = "LOGIN", "Signed in"
        LOGOUT = "LOGOUT", "Signed out"
        VIEW = "VIEW", "Opened document"
        DOWNLOAD = "DOWNLOAD", "Downloaded file"
        CREATE = "CREATE", "Filed document"
        UPDATE = "UPDATE", "Edited document"
        DELETE = "DELETE", "Removed document"
        RESTORE = "RESTORE", "Restored document"
        SEARCH = "SEARCH", "Ran a search"
        USER_MANAGE = "USER_MANAGE", "Managed an account"
        DENIED = "DENIED", "Access denied"
        IMPORT = "IMPORT", "Bulk import"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="access_logs"
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    document = models.ForeignKey(
        Document, on_delete=models.SET_NULL, blank=True, null=True, related_name="access_logs"
    )
    note = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["-timestamp"]), models.Index(fields=["action"])]

    def __str__(self):
        who = self.user.username if self.user else "anonymous"
        return f"{self.timestamp:%Y-%m-%d %H:%M} {who} {self.action}"

    @staticmethod
    def client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    @classmethod
    def record(cls, request, action, document=None, note=""):
        cls.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            document=document,
            note=note[:255],
            ip_address=cls.client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )


class Notification(models.Model):
    """A short, dismissable alert about document activity, polled by the bell icon in the UI."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    verb = models.CharField(max_length=255)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, blank=True, null=True, related_name="notifications"
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]

    def __str__(self):
        return f"{self.recipient}: {self.verb}"

    def get_absolute_url(self):
        return self.document.get_absolute_url() if self.document else ""

    @classmethod
    def notify(cls, recipients, actor, verb, document=None):
        """Fan out one notification per recipient, skipping the actor themself."""
        cls.objects.bulk_create([
            cls(recipient=recipient, actor=actor, verb=verb, document=document)
            for recipient in recipients
            if recipient.pk != getattr(actor, "pk", None)
        ])


class ImportBatch(models.Model):
    """One CSV upload, dry-run validated and then optionally committed.

    The two-phase split matters: nothing in ImportRow ever touches Document
    until commit(), and commit() is all-or-nothing inside one transaction.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Uploaded"
        VALIDATED = "VALIDATED", "Validated"
        COMMITTED = "COMMITTED", "Committed"
        FAILED = "FAILED", "Failed"

    file = models.FileField("CSV file", upload_to=import_upload_path)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="import_batches"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rows_read = models.PositiveIntegerField(default=0)
    rows_ready = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    error_summary = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(blank=True, null=True)
    committed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Import batch #{self.pk} ({self.get_status_display()})"

    @property
    def has_blocking_errors(self) -> bool:
        return self.rows.filter(row_status=ImportRow.RowStatus.ERROR).exists()


class ImportRow(models.Model):
    """One line of an ImportBatch's CSV. Kept even after commit so an
    administrator can see exactly what happened instead of re-deriving it.
    """

    class RowStatus(models.TextChoices):
        OK = "OK", "Ready"
        WARNING = "WARNING", "Ready, with a note"
        ERROR = "ERROR", "Blocked"

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    line_number = models.PositiveIntegerField()
    raw_data = models.JSONField()
    parsed_data = models.JSONField(blank=True, null=True)
    row_status = models.CharField(max_length=8, choices=RowStatus.choices)
    messages = models.JSONField(default=list, blank=True)
    document = models.ForeignKey(
        Document, on_delete=models.SET_NULL, blank=True, null=True, related_name="import_row"
    )

    class Meta:
        ordering = ["batch", "line_number"]
        indexes = [models.Index(fields=["batch", "row_status"])]

    def __str__(self):
        return f"Batch #{self.batch_id} line {self.line_number} ({self.row_status})"


class ScanBatch(models.Model):
    """One bulk upload of scanned PDFs, matched against existing Document
    records by filename and attached on commit. Mirrors ImportBatch's
    stage-then-commit shape.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Staged"
        REVIEWED = "REVIEWED", "Reviewed"
        COMMITTED = "COMMITTED", "Committed"
        FAILED = "FAILED", "Failed"

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="scan_batches"
    )
    filename_pattern = models.CharField(max_length=100, default="{TYPE}-{NUMBER}-{YEAR}.pdf")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Scan batch #{self.pk} ({self.get_status_display()})"


class ScanFile(models.Model):
    """One staged PDF within a ScanBatch, and the Document it was matched to."""

    class MatchStatus(models.TextChoices):
        MATCHED = "MATCHED", "Matched"
        UNMATCHED = "UNMATCHED", "No match"
        CONFLICT = "CONFLICT", "File already on record"
        MANUAL = "MANUAL", "Picked by hand"
        ATTACHED = "ATTACHED", "Attached"
        SKIPPED = "SKIPPED", "Skipped"

    batch = models.ForeignKey(ScanBatch, on_delete=models.CASCADE, related_name="files")
    original_filename = models.CharField(max_length=255)
    staged_file = models.FileField(upload_to=scan_stage_upload_path)
    parsed_doc_type = models.CharField(max_length=8, blank=True)
    parsed_number = models.PositiveIntegerField(blank=True, null=True)
    parsed_series_year = models.PositiveIntegerField(blank=True, null=True)
    document = models.ForeignKey(
        Document, on_delete=models.SET_NULL, blank=True, null=True, related_name="scan_file"
    )
    match_status = models.CharField(max_length=10, choices=MatchStatus.choices)
    resolution = models.CharField(max_length=10, blank=True)
    messages = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["batch", "original_filename"]

    def __str__(self):
        return f"{self.original_filename} ({self.match_status})"
