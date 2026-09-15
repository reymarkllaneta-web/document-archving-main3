from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("records/", views.DocumentListView.as_view(), name="document_list"),
    path("records/new/", views.DocumentCreateView.as_view(), name="document_create"),
    path("records/<int:pk>/", views.DocumentDetailView.as_view(), name="document_detail"),
    path("records/<int:pk>/edit/", views.DocumentUpdateView.as_view(), name="document_update"),
    path("records/<int:pk>/remove/", views.DocumentDeleteView.as_view(), name="document_delete"),
    path("records/<int:pk>/restore/", views.document_restore, name="document_restore"),
    path("records/<int:pk>/file/", views.document_download, name="document_download"),
    path("records/<int:pk>/attachments/", views.attachment_add, name="attachment_add"),
    path("attachments/<int:pk>/file/", views.attachment_download, name="attachment_download"),
    path("bin/", views.RecycleBinView.as_view(), name="recycle_bin"),
    path("export.csv", views.export_csv, name="export_csv"),
    path("audit-trail/", views.AuditTrailView.as_view(), name="audit_trail"),
]
