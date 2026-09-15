from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class ArchiveUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "role", "office", "is_active")
    list_filter = ("role", "is_active", "office")
    fieldsets = UserAdmin.fieldsets + (
        ("Archive profile", {"fields": ("role", "office", "position", "contact_number")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Archive profile", {"fields": ("role", "office", "position", "contact_number")}),
    )
