from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.urls import reverse

from .access import OWNER_ONLY_LABELS, can_open, display_name, set_current_user

OPEN_PATHS = ("/login/", "/first-time/", "/demo-login/", "/static/", "/media/")


class AdminOnlyMiddleware:
    """
    Every page needs a login. On the very first run, ask to create the owner's password.
    Office staff only reach the pages the owner has switched on for them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, "user", None))
        try:
            path = request.path
            if not path.startswith(OPEN_PATHS):
                if not get_user_model().objects.exists():
                    return redirect(reverse("office:first_time"))
                if not request.user.is_authenticated:
                    return redirect(f"{reverse('office:login')}?next={path}")
            return self.get_response(request)
        finally:
            set_current_user(None)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if not match or match.namespace != "office" or not request.user.is_authenticated:
            return None
        if can_open(request.user, match.url_name):
            return None
        what = OWNER_ONLY_LABELS.get(match.url_name, "open this page")
        # Write it in the activity log when someone tries to change something, or opens a money / owner page.
        if request.method == "POST" or match.url_name in OWNER_ONLY_LABELS:
            from .models import ActivityLog
            ActivityLog.add("security", f"{display_name(request.user)} tried to {what} — blocked")
        return render(request, "office/forbidden.html", {"what": what}, status=403)
