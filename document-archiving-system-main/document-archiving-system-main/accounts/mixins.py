from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class StaffUserRequiredMixin(LoginRequiredMixin):
    """Any signed-in, active account. Read-only access to the archive."""


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Administrators only. Everything that writes to the archive."""

    def test_func(self):
        return self.request.user.is_archive_admin

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Administrator access is required for this page.")
        return super().handle_no_permission()
