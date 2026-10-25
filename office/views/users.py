"""Logins: the owner adds office staff and chooses what each one may do."""
import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..access import PERMISSION_KEYS, PERMISSIONS
from ..forms import StaffUserForm
from ..models import ActivityLog, StaffAccess

User = get_user_model()


def _staff():
    return User.objects.filter(is_superuser=False, staff_access__isnull=False).select_related("staff_access")


def users(request):
    rows = []
    for u in _staff().order_by("-is_active", "first_name"):
        a = u.staff_access
        rows.append({"u": u, "allowed": [label for key, label, _ in PERMISSIONS if getattr(a, key)]})
    return render(request, "office/users.html", {"rows": rows, "permissions": PERMISSIONS})


def _apply(user, form):
    access, _ = StaffAccess.objects.get_or_create(user=user)
    for key in PERMISSION_KEYS:
        setattr(access, key, form.cleaned_data[key])
    access.save()


def user_create(request):
    form = StaffUserForm(request.POST or None, initial={"fees": True, "attendance": True, "students": True})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            u = User.objects.create_user("staff_" + secrets.token_hex(4), password=form.cleaned_data["password1"],
                                         first_name=form.cleaned_data["name"])
            _apply(u, form)
        ActivityLog.add("login", f"New office login made for {u.first_name}", link="/logins/")
        messages.success(request, f"Login made for {u.first_name}. They choose their name on the login screen.")
        return redirect("office:users")
    return render(request, "office/user_form.html", {"form": form, "title": "Add office staff"})


def user_edit(request, pk):
    u = get_object_or_404(_staff(), pk=pk)
    a = u.staff_access
    form = StaffUserForm(request.POST or None, instance=u,
                         initial={"name": u.first_name, **{k: getattr(a, k) for k in PERMISSION_KEYS}})
    if request.method == "POST" and form.is_valid():
        u.first_name = form.cleaned_data["name"]
        if form.cleaned_data.get("password1"):
            u.set_password(form.cleaned_data["password1"])
        u.save()
        _apply(u, form)
        ActivityLog.add("login", f"Changed {u.first_name}'s login"
                                 + (" (new password)" if form.cleaned_data.get("password1") else ""), link="/logins/")
        messages.success(request, f"{u.first_name}'s login saved.")
        return redirect("office:users")
    return render(request, "office/user_form.html", {"form": form, "title": f"{u.first_name}'s login", "u": u})


@require_POST
def user_toggle(request, pk):
    u = get_object_or_404(_staff(), pk=pk)
    u.is_active = not u.is_active
    u.save(update_fields=["is_active"])
    if u.is_active:
        ActivityLog.add("login", f"Turned {u.first_name}'s login back on", link="/logins/")
        messages.success(request, f"{u.first_name} can log in again.")
    else:
        ActivityLog.add("login", f"Turned off {u.first_name}'s login", link="/logins/")
        messages.success(request, f"{u.first_name} can no longer log in. Their past work stays in the records.")
    return redirect("office:users")
