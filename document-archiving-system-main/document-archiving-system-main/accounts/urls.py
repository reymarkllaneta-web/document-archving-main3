from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("sign-in/", views.ArchiveLoginView.as_view(), name="login"),
    path("sign-out/", views.ArchiveLogoutView.as_view(), name="logout"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("password/", views.ChangeOwnPasswordView.as_view(), name="password_change"),
    path("notifications/", views.NotificationListView.as_view(), name="notification_list"),
    path("notifications/poll/", views.notifications_poll, name="notifications_poll"),
    path("notifications/<int:pk>/open/", views.notification_open, name="notification_open"),
    path("notifications/mark-all-read/", views.notifications_mark_all_read, name="notifications_mark_all_read"),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/new/", views.UserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/edit/", views.UserUpdateView.as_view(), name="user_update"),
    path("users/<int:pk>/reset-password/", views.UserPasswordResetView.as_view(), name="user_password"),
]
