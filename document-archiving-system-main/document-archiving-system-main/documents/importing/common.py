"""Bits shared by the CSV import engine and the scan-attach engine."""
import os

from django.conf import settings


class ImportNotReady(Exception):
    """Raised when commit() is called on a batch that isn't eligible yet."""


def validate_upload_file(upload) -> list[str]:
    """Size + extension checks against the same limits DocumentForm.clean_file
    enforces. Pure function returning problem strings (empty = OK) so both a
    ModelForm's clean_file and the scan-attach engine (which never builds a
    ModelForm) can reuse the exact same rule.
    """
    problems = []
    if upload.size > settings.MAX_UPLOAD_SIZE:
        limit = settings.MAX_UPLOAD_SIZE // (1024 * 1024)
        problems.append(f"That file is larger than the {limit} MB limit.")
    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_UPLOAD_EXTENSIONS)
        problems.append(f"Upload one of these file types: {allowed}.")
    return problems
