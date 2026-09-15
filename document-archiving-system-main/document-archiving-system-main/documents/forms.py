from datetime import date

from django import forms
from django.conf import settings

from .importing.common import validate_upload_file
from .models import Attachment, Document, DocumentType


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            "doc_type", "series_year", "number",
            "subject", "description", "date_issued", "effectivity_date",
            "originating_office", "signatory", "addressee", "keywords",
            "status", "classification",
            "file", "page_count", "physical_location",
            "related_to", "indorsement_level",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "date_issued": forms.DateInput(attrs={"type": "date"}),
            "effectivity_date": forms.DateInput(attrs={"type": "date"}),
            "subject": forms.TextInput(attrs={"placeholder": "Subject line as written on the document"}),
            "keywords": forms.TextInput(attrs={"placeholder": "budget, travel order, 2026"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["related_to"].queryset = Document.objects.filter(is_deleted=False)
        self.fields["number"].required = False
        if not self.instance.pk:
            self.fields["number"].help_text = (
                "Leave blank and the next number in this series is assigned on save."
            )

    def clean_series_year(self):
        year = self.cleaned_data["series_year"]
        if not (1900 <= year <= date.today().year + 1):
            raise forms.ValidationError("Enter a series year between 1900 and next year.")
        return year

    def clean_file(self):
        upload = self.cleaned_data.get("file")
        if not upload or not hasattr(upload, "size"):
            return upload
        problems = validate_upload_file(upload)
        if problems:
            raise forms.ValidationError(problems[0])
        return upload

    def clean(self):
        cleaned = super().clean()
        doc_type = cleaned.get("doc_type")
        number = cleaned.get("number")
        year = cleaned.get("series_year")

        if doc_type == DocumentType.INDORSEMENT and not cleaned.get("indorsement_level"):
            self.add_error("indorsement_level", "Say which indorsement this is: 1, 2, 3 …")
        if doc_type != DocumentType.INDORSEMENT:
            cleaned["indorsement_level"] = None

        if doc_type and number and year:
            clash = Document.objects.filter(
                doc_type=doc_type, series_year=year, number=number
            ).exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error(
                    "number",
                    f"{clash.first().control_number} is already on file. Pick another number.",
                )

        related = cleaned.get("related_to")
        if related and self.instance.pk and related.pk == self.instance.pk:
            self.add_error("related_to", "A document cannot refer to itself.")
        return cleaned


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["label", "file"]

    def clean_file(self):
        upload = self.cleaned_data.get("file")
        if upload and upload.size > settings.MAX_UPLOAD_SIZE:
            limit = settings.MAX_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"That file is larger than the {limit} MB limit.")
        return upload


class DocumentSearchForm(forms.Form):
    """Every field is optional; blanks are ignored."""

    q = forms.CharField(
        required=False, label="Keyword",
        widget=forms.TextInput(attrs={
            "placeholder": "Subject, office, signatory, tag…",
            "autofocus": True, "autocomplete": "off",
        }),
    )
    doc_type = forms.ChoiceField(
        required=False, label="Type",
        choices=[("", "All types")] + list(DocumentType.choices),
    )
    number = forms.IntegerField(required=False, min_value=1, label="No.")
    series_year = forms.IntegerField(required=False, min_value=1900, label="Series")
    status = forms.ChoiceField(
        required=False, label="Status",
        choices=[("", "Any status")] + list(Document.Status.choices),
    )
    office = forms.CharField(required=False, label="Originating office")
    date_from = forms.DateField(
        required=False, label="Issued from", widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        required=False, label="Issued to", widget=forms.DateInput(attrs={"type": "date"})
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_from"), cleaned.get("date_to")
        if start and end and start > end:
            self.add_error("date_to", "The end date falls before the start date.")
        return cleaned

    def filter(self, queryset):
        if not self.is_valid():
            return queryset
        data = self.cleaned_data
        qs = queryset.search(data.get("q"))
        if data.get("doc_type"):
            qs = qs.filter(doc_type=data["doc_type"])
        if data.get("number"):
            qs = qs.filter(number=data["number"])
        if data.get("series_year"):
            qs = qs.filter(series_year=data["series_year"])
        if data.get("status"):
            qs = qs.filter(status=data["status"])
        if data.get("office"):
            qs = qs.filter(originating_office__icontains=data["office"])
        if data.get("date_from"):
            qs = qs.filter(date_issued__gte=data["date_from"])
        if data.get("date_to"):
            qs = qs.filter(date_issued__lte=data["date_to"])
        return qs

    @property
    def is_filtered(self):
        return any(self.data.get(name) for name in self.fields)

    def summary(self):
        if not self.is_valid():
            return ""
        bits = []
        for name, value in self.cleaned_data.items():
            if value:
                bits.append(f"{name}={value}")
        return "; ".join(bits)
