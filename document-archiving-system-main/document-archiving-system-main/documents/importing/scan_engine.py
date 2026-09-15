"""Bulk scan-attach: pair a folder of PDFs to Document records that already
exist, by parsing each filename against a configurable pattern.

Mirrors csv_engine's stage-then-commit shape:

  stage_files() — dry run. Validates and matches every file, persists
    ScanBatch + ScanFile, attaches nothing.

  commit() — attaches matched files to their Document inside one
    transaction. A record that already has a scan is flagged CONFLICT and
    is only replaced if the administrator explicitly says so.
"""
import re

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from .common import ImportNotReady, validate_upload_file
from .csv_engine import DOC_TYPE_ALIASES
from ..models import Document, ScanBatch, ScanFile

_PATTERN_TOKENS = {
    "TYPE": r"(?P<type>[A-Za-z]+)",
    "NUMBER": r"(?P<number>\d+)",
    "YEAR": r"(?P<year>\d{4})",
}


def _compile_pattern(pattern: str):
    escaped = re.escape(pattern)
    for token, group in _PATTERN_TOKENS.items():
        escaped = escaped.replace(re.escape("{" + token + "}"), group)
    return re.compile(f"^{escaped}$", re.IGNORECASE)


def parse_filename(filename: str, pattern: str):
    """Returns {"type_raw", "number_raw", "year_raw"} or None if it doesn't match."""
    match = _compile_pattern(pattern).match(filename)
    if not match:
        return None
    groups = match.groupdict()
    return {
        "type_raw": groups.get("type", ""),
        "number_raw": groups.get("number", ""),
        "year_raw": groups.get("year", ""),
    }


def stage_files(files, *, pattern: str, uploaded_by) -> ScanBatch:
    batch = ScanBatch.objects.create(uploaded_by=uploaded_by, filename_pattern=pattern)

    for upload in files:
        parsed = parse_filename(upload.name, pattern)
        messages = []
        match_status = ScanFile.MatchStatus.UNMATCHED
        document = None
        parsed_doc_type = ""
        parsed_number = None
        parsed_series_year = None

        problems = validate_upload_file(upload)
        if problems:
            messages.extend(problems)
        elif not parsed:
            messages.append(f"Filename doesn't match the pattern {pattern}.")
        else:
            doc_type = DOC_TYPE_ALIASES.get(parsed["type_raw"].lower())
            if not doc_type:
                messages.append(f"'{parsed['type_raw']}' isn't a recognized document type.")
            else:
                parsed_doc_type = doc_type
                try:
                    parsed_number = int(parsed["number_raw"])
                    parsed_series_year = int(parsed["year_raw"])
                except ValueError:
                    messages.append("Couldn't read the number or year from this filename.")
                    parsed_number = None
                    parsed_series_year = None
                else:
                    document = Document.objects.filter(
                        doc_type=doc_type, number=parsed_number,
                        series_year=parsed_series_year, is_deleted=False,
                    ).first()
                    if not document:
                        messages.append(
                            f"No record found for {doc_type}-{parsed_number:03d}-{parsed_series_year}."
                        )
                    elif document.file:
                        match_status = ScanFile.MatchStatus.CONFLICT
                        messages.append(f"{document.control_number} already has a scan on file.")
                    else:
                        match_status = ScanFile.MatchStatus.MATCHED

        scan_file = ScanFile(
            batch=batch, original_filename=upload.name, staged_file=upload,
            parsed_doc_type=parsed_doc_type, parsed_number=parsed_number,
            parsed_series_year=parsed_series_year, document=document,
            match_status=match_status, messages=messages,
        )
        scan_file.save()

    batch.status = ScanBatch.Status.REVIEWED
    batch.save(update_fields=["status"])
    return batch


def commit(batch: ScanBatch, decisions: dict, *, acting_user=None) -> ScanBatch:
    """decisions: {scan_file_id (str or int): {"decision": "attach"|"replace"|"skip",
    "document_id": int|None}} — document_id lets the administrator hand-pick a match
    for an UNMATCHED file from the review page."""
    if batch.status not in (ScanBatch.Status.PENDING, ScanBatch.Status.REVIEWED):
        raise ImportNotReady("This batch has already been committed.")

    try:
        with transaction.atomic():
            files = list(batch.files.select_related("document").order_by("original_filename"))
            for scan_file in files:
                choice = decisions.get(str(scan_file.pk)) or decisions.get(scan_file.pk) or {}
                decision = choice.get("decision") or "attach"
                document_id = choice.get("document_id")

                target = scan_file.document
                if document_id:
                    target = Document.objects.filter(pk=document_id, is_deleted=False).first()

                if decision == "skip" or not target:
                    scan_file.match_status = ScanFile.MatchStatus.SKIPPED
                    scan_file.resolution = "skip"
                    scan_file.save(update_fields=["match_status", "resolution"])
                    continue

                if target.file and decision != "replace":
                    scan_file.match_status = ScanFile.MatchStatus.CONFLICT
                    scan_file.messages = scan_file.messages + [
                        "Skipped: this record already has a scan and replace wasn't confirmed."
                    ]
                    scan_file.save(update_fields=["match_status", "messages"])
                    continue

                revalidated = validate_upload_file(scan_file.staged_file)
                if revalidated:
                    scan_file.messages = scan_file.messages + revalidated
                    scan_file.match_status = ScanFile.MatchStatus.SKIPPED
                    scan_file.save(update_fields=["messages", "match_status"])
                    continue

                with scan_file.staged_file.open("rb") as fh:
                    target.file.save(scan_file.original_filename, File(fh), save=False)
                target.updated_by = acting_user
                target.save()

                scan_file.document = target
                scan_file.match_status = ScanFile.MatchStatus.ATTACHED
                scan_file.resolution = decision
                scan_file.save(update_fields=["document", "match_status", "resolution"])

            batch.status = ScanBatch.Status.COMMITTED
            batch.committed_at = timezone.now()
            batch.save(update_fields=["status", "committed_at"])
    except Exception:
        batch.status = ScanBatch.Status.FAILED
        batch.save(update_fields=["status"])
        raise
    return batch
