import csv
from datetime import date

from django.contrib import messages
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from accounts.mixins import AdminRequiredMixin, StaffUserRequiredMixin
from accounts.models import User

from .forms import AttachmentForm, DocumentForm, DocumentSearchForm
from .models import AccessLog, Attachment, Document, DocumentType, Notification


TYPE_ICONS = {
    DocumentType.MEMORANDUM: "icon-file-text",
    DocumentType.INDORSEMENT: "icon-send",
    DocumentType.OFFICE_ORDER: "icon-clipboard",
    DocumentType.EXECUTIVE_ORDER: "icon-shield",
}


class DashboardView(StaffUserRequiredMixin, TemplateView):
    template_name = "documents/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visible = Document.objects.visible_to(self.request.user)
        this_year = date.today().year

        counts = {row["doc_type"]: row["n"] for row in
                  visible.values("doc_type").annotate(n=Count("id"))}
        context["type_cards"] = [
            {
                "code": code,
                "label": label,
                "icon": TYPE_ICONS.get(code, "icon-file-text"),
                "total": counts.get(code, 0),
                "this_year": visible.filter(doc_type=code, series_year=this_year).count(),
                "last_number": Document.next_number(code, this_year) - 1,
            }
            for code, label in DocumentType.choices
        ]
        context["total"] = visible.count()
        context["this_year"] = this_year
        context["recent"] = visible.select_related("created_by")[:8]
        context["latest_filed"] = visible.order_by("-created_at")[:6]
        return context


class DocumentListView(StaffUserRequiredMixin, ListView):
    template_name = "documents/document_list.html"
    context_object_name = "documents"
    paginate_by = 20

    def get_queryset(self):
        self.form = DocumentSearchForm(self.request.GET or None)
        qs = Document.objects.visible_to(self.request.user).select_related("created_by")
        if self.request.GET:
            qs = self.form.filter(qs)
        return qs

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        if request.GET and getattr(self, "form", None) and self.form.is_filtered:
            AccessLog.record(request, AccessLog.Action.SEARCH, note=self.form.summary())
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = self.form
        querystring = self.request.GET.copy()
        querystring.pop("page", None)
        context["querystring"] = querystring.urlencode()
        return context


class DocumentDetailView(StaffUserRequiredMixin, DetailView):
    template_name = "documents/document_detail.html"
    context_object_name = "document"

    def get_queryset(self):
        return Document.objects.visible_to(self.request.user).select_related(
            "created_by", "updated_by", "related_to"
        )

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        AccessLog.record(request, AccessLog.Action.VIEW, document=self.object)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attachment_form"] = AttachmentForm()
        context["chain"] = self.object.referenced_by.filter(is_deleted=False)
        if self.request.user.is_archive_admin:
            context["history"] = self.object.access_logs.select_related("user")[:15]
        return context


class DocumentCreateView(AdminRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = "documents/document_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        AccessLog.record(self.request, AccessLog.Action.CREATE, document=self.object)
        Notification.notify(
            recipients=User.objects.filter(is_active=True),
            actor=self.request.user,
            verb=f"filed {self.object.control_number} — {self.object.subject}",
            document=self.object,
        )
        messages.success(self.request, f"{self.object.control_number} filed.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["heading"] = "File a new document"
        return context


class DocumentUpdateView(AdminRequiredMixin, UpdateView):
    model = Document
    form_class = DocumentForm
    template_name = "documents/document_form.html"

    def get_queryset(self):
        return Document.objects.filter(is_deleted=False)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        changed = ", ".join(form.changed_data) or "no field changes"
        AccessLog.record(
            self.request, AccessLog.Action.UPDATE, document=self.object, note=changed
        )
        Notification.notify(
            recipients=[self.object.created_by],
            actor=self.request.user,
            verb=f"updated {self.object.control_number} — {self.object.subject}",
            document=self.object,
        )
        messages.success(self.request, f"{self.object.control_number} updated.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["heading"] = f"Edit {self.object.control_number}"
        return context


class DocumentDeleteView(AdminRequiredMixin, DeleteView):
    model = Document
    template_name = "documents/document_confirm_delete.html"
    success_url = reverse_lazy("documents:document_list")
    context_object_name = "document"

    def get_queryset(self):
        return Document.objects.filter(is_deleted=False)

    def form_valid(self, form):
        """Soft delete: the record moves to the bin, the control number stays taken."""
        self.object = self.get_object()
        control = self.object.control_number
        self.object.soft_delete()
        AccessLog.record(self.request, AccessLog.Action.DELETE, document=self.object)
        Notification.notify(
            recipients=[self.object.created_by],
            actor=self.request.user,
            verb=f"removed {control} to the bin",
        )
        messages.success(self.request, f"{control} moved to the bin. An administrator can restore it.")
        return redirect(self.success_url)


class RecycleBinView(AdminRequiredMixin, ListView):
    template_name = "documents/recycle_bin.html"
    context_object_name = "documents"
    paginate_by = 25

    def get_queryset(self):
        return Document.objects.filter(is_deleted=True).select_related("created_by")


def document_restore(request, pk):
    if not request.user.is_authenticated or not request.user.is_archive_admin:
        AccessLog.record(request, AccessLog.Action.DENIED, note=f"restore document {pk}")
        raise Http404
    document = get_object_or_404(Document, pk=pk, is_deleted=True)
    document.restore()
    AccessLog.record(request, AccessLog.Action.RESTORE, document=document)
    Notification.notify(
        recipients=[document.created_by],
        actor=request.user,
        verb=f"restored {document.control_number} — {document.subject}",
        document=document,
    )
    messages.success(request, f"{document.control_number} restored.")
    return redirect("documents:recycle_bin")


def _serve(request, file_field, document, action):
    if not file_field:
        raise Http404("No file is attached to this record.")
    AccessLog.record(request, action, document=document)
    return FileResponse(file_field.open("rb"), as_attachment=True,
                        filename=file_field.name.split("/")[-1])


def document_download(request, pk):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    document = get_object_or_404(Document.objects.visible_to(request.user), pk=pk)
    return _serve(request, document.file, document, AccessLog.Action.DOWNLOAD)


def attachment_download(request, pk):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    attachment = get_object_or_404(Attachment, pk=pk)
    if not Document.objects.visible_to(request.user).filter(pk=attachment.document_id).exists():
        AccessLog.record(request, AccessLog.Action.DENIED, note=f"attachment {pk}")
        raise Http404
    return _serve(request, attachment.file, attachment.document, AccessLog.Action.DOWNLOAD)


def attachment_add(request, pk):
    if not request.user.is_authenticated or not request.user.is_archive_admin:
        AccessLog.record(request, AccessLog.Action.DENIED, note=f"add attachment to {pk}")
        raise Http404
    document = get_object_or_404(Document, pk=pk, is_deleted=False)
    if request.method != "POST":
        return redirect(document)
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.document = document
        attachment.uploaded_by = request.user
        attachment.save()
        AccessLog.record(
            request, AccessLog.Action.UPDATE, document=document,
            note=f"Added enclosure: {attachment.label}",
        )
        messages.success(request, f"Enclosure “{attachment.label}” added.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect(document)


def export_csv(request):
    """Export the current search result as CSV. Administrators only."""
    if not request.user.is_authenticated or not request.user.is_archive_admin:
        AccessLog.record(request, AccessLog.Action.DENIED, note="csv export")
        raise Http404
    form = DocumentSearchForm(request.GET or None)
    qs = Document.objects.visible_to(request.user)
    if request.GET:
        qs = form.filter(qs)

    response = HttpResponse(content_type="text/csv")
    stamp = date.today().isoformat()
    response["Content-Disposition"] = f'attachment; filename="archive-index-{stamp}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Control number", "Type", "Series", "No.", "Subject", "Date issued",
        "Originating office", "Signed by", "Status", "Classification", "Filed by", "Filed on",
    ])
    for doc in qs.select_related("created_by").iterator():
        writer.writerow([
            doc.control_number, doc.get_doc_type_display(), doc.series_year, doc.number,
            doc.subject, doc.date_issued, doc.originating_office, doc.signatory,
            doc.get_status_display(), doc.get_classification_display(),
            doc.created_by.username, doc.created_at.strftime("%Y-%m-%d %H:%M"),
        ])
    AccessLog.record(request, AccessLog.Action.DOWNLOAD, note=f"CSV export ({qs.count()} rows)")
    return response


class AuditTrailView(AdminRequiredMixin, ListView):
    template_name = "documents/audit_trail.html"
    context_object_name = "entries"
    paginate_by = 50

    def get_queryset(self):
        qs = AccessLog.objects.select_related("user", "document")
        action = self.request.GET.get("action")
        username = self.request.GET.get("user")
        if action:
            qs = qs.filter(action=action)
        if username:
            qs = qs.filter(user__username__icontains=username)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["actions"] = AccessLog.Action.choices
        context["selected_action"] = self.request.GET.get("action", "")
        context["selected_user"] = self.request.GET.get("user", "")
        return context
