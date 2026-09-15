from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import AdminPasswordChangeForm, PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, UpdateView

from documents.models import AccessLog, Notification

from .forms import ArchiveLoginForm, ProfileForm, UserCreateForm, UserUpdateForm
from .mixins import AdminRequiredMixin
from .models import User


class ArchiveLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = ArchiveLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        AccessLog.record(self.request, action=AccessLog.Action.LOGIN)
        return response


class ArchiveLogoutView(LogoutView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            AccessLog.record(request, action=AccessLog.Action.LOGOUT)
        return super().dispatch(request, *args, **kwargs)


class ProfileView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Profile updated.")
        return response


class ChangeOwnPasswordView(LoginRequiredMixin, FormView):
    template_name = "accounts/password_change.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("documents:dashboard")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "Password changed.")
        return super().form_valid(form)


class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(username__icontains=q) | qs.filter(last_name__icontains=q) | qs.filter(office__icontains=q)
        return qs.distinct()


class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Account created for {self.object.username}.")
        AccessLog.record(
            self.request,
            action=AccessLog.Action.USER_MANAGE,
            note=f"Created account {self.object.username} ({self.object.role_label})",
        )
        return response


class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["editing_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Account {self.object.username} updated.")
        AccessLog.record(
            self.request,
            action=AccessLog.Action.USER_MANAGE,
            note=f"Updated account {self.object.username} ({self.object.role_label})",
        )
        return response


class UserPasswordResetView(AdminRequiredMixin, FormView):
    template_name = "accounts/user_password.html"
    form_class = AdminPasswordChangeForm
    success_url = reverse_lazy("accounts:user_list")

    def get_target(self):
        return get_object_or_404(User, pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.get_target()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target_user"] = self.get_target()
        return context

    def form_valid(self, form):
        form.save()
        messages.success(self.request, f"New password set for {form.user.username}.")
        AccessLog.record(
            self.request,
            action=AccessLog.Action.USER_MANAGE,
            note=f"Reset password for {form.user.username}",
        )
        return super().form_valid(form)


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "accounts/notification_list.html"
    context_object_name = "notification_list"
    paginate_by = 30

    def get_queryset(self):
        return self.request.user.notifications.select_related("document", "actor")

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return response


def notifications_poll(request):
    """Polled every few seconds by the bell icon; returns a rendered fragment plus an unread count header."""
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    items = request.user.notifications.select_related("document", "actor")[:8]
    unread = request.user.notifications.filter(is_read=False).count()
    html = render_to_string(
        "accounts/_notification_items.html", {"notification_items": items}, request=request
    )
    response = HttpResponse(html)
    response["X-Unread-Count"] = str(unread)
    return response


def notification_open(request, pk):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect(notification.get_absolute_url() or "documents:dashboard")


def notifications_mark_all_read(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect(request.META.get("HTTP_REFERER") or "documents:dashboard")
