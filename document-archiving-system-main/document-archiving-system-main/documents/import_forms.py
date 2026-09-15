import os

from django import forms
from django.conf import settings


class ImportUploadForm(forms.Form):
    file = forms.FileField(label="CSV file")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if os.path.splitext(upload.name)[1].lower() != ".csv":
            raise forms.ValidationError("Upload a .csv file.")
        if upload.size > settings.MAX_UPLOAD_SIZE:
            limit = settings.MAX_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"That file is larger than the {limit} MB limit.")
        return upload


class ScanUploadForm(forms.Form):
    """The multi-file list itself is read from request.FILES.getlist("files")
    in the view — a plain FileField only ever binds to one file."""

    filename_pattern = forms.CharField(
        label="Filename pattern", initial="{TYPE}-{NUMBER}-{YEAR}.pdf",
        help_text="TYPE, NUMBER and YEAR are the placeholders the matcher looks for, "
                   "e.g. MEMO-012-2019.pdf finds MEMORANDUM No. 012, s. 2019.",
    )
