def notifications(request):
    if not request.user.is_authenticated:
        return {}
    qs = request.user.notifications.select_related("document", "actor")
    return {
        "notification_items": qs[:8],
        "unread_notification_count": qs.filter(is_read=False).count(),
    }
