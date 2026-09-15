import os
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


def avatar_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"avatars/{uuid.uuid4().hex}{ext}"


class User(AbstractUser):
    """Records-office user. Two roles only: Administrator and Staff user."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        USER = "USER", "Staff user"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)
    office = models.CharField("Office or division", max_length=120, blank=True)
    position = models.CharField(max_length=120, blank=True)
    contact_number = models.CharField(max_length=32, blank=True)
    avatar = models.ImageField("Profile picture", upload_to=avatar_upload_path, blank=True, null=True)

    class Meta:
        ordering = ["last_name", "first_name", "username"]

    def __str__(self):
        full = self.get_full_name()
        return f"{full} ({self.username})" if full else self.username

    @property
    def is_archive_admin(self) -> bool:
        """Superusers are always treated as administrators."""
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def role_label(self) -> str:
        return "Administrator" if self.is_archive_admin else "Staff user"

    @property
    def initials(self) -> str:
        letters = (self.first_name[:1] + self.last_name[:1]).upper()
        return letters or self.username[:2].upper()
