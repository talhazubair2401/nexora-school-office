from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..access import OWNER_USERNAME, can_open, display_name, is_owner, set_current_user
from ..forms import ChangePasswordForm, NewPasswordForm, PasswordLoginForm, StaffLoginForm
from ..models import ActivityLog

User = get_user_model()
ADMIN = OWNER_USERNAME


def first_time(request):
    """Shown once, on the very first start: choose the owner's (admin) password."""
    if User.objects.exists():
        return redirect("office:login")
    form = NewPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(ADMIN, password=form.cleaned_data["password1"],
                                        is_staff=True, is_superuser=True)
        login(request, user)
        messages.success(request, "Password saved. Welcome to the office system.")
        return redirect("office:dashboard")
    return render(request, "auth/first_time.html", {"form": form})


def _go_next(request, user):
    from django.urls import resolve, Resolver404
    nxt = request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        try:
            if can_open(user, resolve(nxt.split("?")[0]).url_name):
                return redirect(nxt)
        except Resolver404:
            pass
    return redirect("office:dashboard")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("office:dashboard")
    from django.conf import settings
    if settings.DEMO_MODE:
        from ..demo import DEMO_ACCOUNTS
        return render(request, "auth/demo_login.html", {"accounts": [
            {"username": u, "label": l, "desc": d, "owner": p is None} for u, l, d, p in DEMO_ACCOUNTS]})
    role = "staff" if request.POST.get("role") == "staff" else "owner"
    staff_users = StaffLoginForm().fields["user"].queryset
    owner_form = PasswordLoginForm(request.POST if role == "owner" and request.method == "POST" else None)
    staff_form = StaffLoginForm(request.POST if role == "staff" and request.method == "POST" else None)
    error = ""
    if request.method == "POST":
        if role == "owner" and owner_form.is_valid():
            user = authenticate(request, username=ADMIN, password=owner_form.cleaned_data["password"])
            if user:
                login(request, user)
                set_current_user(user)
                ActivityLog.add("login", "Principal logged in")
                return _go_next(request, user)
            error = "That password is not right. Check Caps Lock and try again."
        elif role == "staff" and staff_form.is_valid():
            chosen = staff_form.cleaned_data["user"]
            user = authenticate(request, username=chosen.username, password=staff_form.cleaned_data["staff_password"])
            if user:
                login(request, user)
                set_current_user(user)
                ActivityLog.add("login", f"{display_name(user)} logged in")
                return _go_next(request, user)
            error = "That password is not right for this name. Check Caps Lock and try again."
        else:
            error = "Please fill in the boxes below."
    return render(request, "auth/login.html", {
        "owner_form": owner_form, "staff_form": staff_form, "role": role, "error": error,
        "has_staff": staff_users.exists(),
    })


BACKUP_EVERY_DAYS = 7


def backup_due():
    """True when no backup was made in the last week."""
    from django.utils import timezone
    from ..models import School
    last = School.get().last_backup_at
    return last is None or (timezone.now() - last).days >= BACKUP_EVERY_DAYS


@require_POST
def logout_view(request):
    # Closing time: remind the owner to back up if it has been a week (or never).
    if is_owner(request.user) and request.POST.get("skip_backup") != "1" and backup_due():
        return redirect("office:closing")
    logout(request)
    return redirect("office:login")


def closing(request):
    """Shown when the owner presses Lock and a backup is due: back up now, or lock without it."""
    from django.utils import timezone
    from ..models import School
    from .tools import removable_drives
    import os
    school = School.get()
    drives = removable_drives()
    folder = school.backup_folder
    # The saved folder is on a USB that is plugged in now? Use it. Otherwise suggest the USB that is plugged in.
    if drives and not (folder and any(folder.upper().startswith(d.upper()) for d in drives)):
        folder = drives[0] + "School backups"
    days = (timezone.now() - school.last_backup_at).days if school.last_backup_at else None
    return render(request, "office/closing.html", {"school": school, "drives": drives, "folder": folder,
                                                   "days": days, "is_windows": os.name == "nt"})


def change_password(request):
    back = "office:settings" if is_owner(request.user) else "office:dashboard"
    form = ChangePasswordForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["password1"])
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, "Password changed. Use the new one next time.")
        return redirect(back)
    return render(request, "office/form_page.html", {"form": form, "title": "Change my password",
                                                      "cancel": back, "button": "Change password"})
