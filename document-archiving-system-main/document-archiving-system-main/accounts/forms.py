import os

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User

AVATAR_MAX_SIZE = 2 * 1024 * 1024
AVATAR_ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]


class ArchiveLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "Username"})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Password"})
    )


class UserCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = [
            "username", "first_name", "last_name", "email",
            "role", "office", "position", "contact_number",
        ]

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email


class ProfileForm(forms.ModelForm):
    """A user editing their own details. No role, office assignment, or active-state control here."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "contact_number", "avatar"]

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email

    def clean_avatar(self):
        upload = self.cleaned_data.get("avatar")
        if not upload or not hasattr(upload, "size"):
            return upload
        if upload.size > AVATAR_MAX_SIZE:
            limit = AVATAR_MAX_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"That image is larger than the {limit} MB limit.")
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in AVATAR_ALLOWED_EXTENSIONS:
            allowed = ", ".join(AVATAR_ALLOWED_EXTENSIONS)
            raise forms.ValidationError(f"Upload one of these image types: {allowed}.")
        return upload


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "email",
            "role", "office", "position", "contact_number", "is_active",
        ]

    def __init__(self, *args, editing_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editing_user = editing_user

    def clean(self):
        cleaned = super().clean()
        # An administrator cannot demote or deactivate their own account and
        # lock themselves out of user management.
        if self.editing_user and self.instance.pk == self.editing_user.pk:
            if cleaned.get("role") != User.Role.ADMIN:
                self.add_error("role", "You cannot remove your own administrator role.")
            if not cleaned.get("is_active"):
                self.add_error("is_active", "You cannot deactivate your own account.")
        return cleaned
