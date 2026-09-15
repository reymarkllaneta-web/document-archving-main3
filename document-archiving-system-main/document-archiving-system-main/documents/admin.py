from django.contrib import admin

from .models import AccessLog, Attachment, Document, Notification


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("control_number", "subject", "date_issued", "status", "classification", "is_deleted")
    list_filter = ("doc_type", "series_year", "status", "classification", "is_deleted")
    search_fields = ("subject", "description", "keywords", "originating_office", "signatory")
    date_hierarchy = "date_issued"
    inlines = [AttachmentInline]
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "document", "ip_address")
    list_filter = ("action",)
    search_fields = ("user__username", "note")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "actor", "verb", "is_read")
    list_filter = ("is_read",)
    search_fields = ("recipient__username", "actor__username", "verb")
