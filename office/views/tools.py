"""Backup, recent activity and other expenses."""
import os
import shutil
import sqlite3
import string
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import connection
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import ExpenseForm
from ..models import ActivityLog, Expense, School, add_months
from .common import paginate, parse_month, safe_next


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def removable_drives():
    """USB sticks and memory cards plugged into this Windows computer, e.g. ['E:\\']."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        out = []
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << i):
                root = f"{letter}:\\"
                if ctypes.windll.kernel32.GetDriveTypeW(root) == 2:   # DRIVE_REMOVABLE
                    out.append(root)
        return out
    except Exception:
        return []


def make_backup(folder):
    """
    Copies the records (db.sqlite3, read safely even while the system is running) and the
    photos (media) into a new dated folder inside `folder`. Never changes the originals.
    Returns (path of the new backup folder, number of students in the copy).
    """
    base = Path(folder).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    stamp = timezone.localtime().strftime("%Y-%m-%d_%H-%M")
    target = base / f"School_backup_{stamp}"
    n = 1
    while target.exists():
        n += 1
        target = base / f"School_backup_{stamp}_{n}"
    target.mkdir()
    db_copy = target / "db.sqlite3"
    connection.ensure_connection()
    dest = sqlite3.connect(str(db_copy))
    try:
        connection.connection.backup(dest)          # SQLite's own safe copy
        ok = dest.execute("PRAGMA integrity_check").fetchone()[0]
        students = dest.execute("SELECT COUNT(*) FROM office_student").fetchone()[0]
    finally:
        dest.close()
    if ok != "ok":
        raise OSError("The copy could not be checked. Please try again.")
    media = Path(settings.MEDIA_ROOT)
    if media.exists() and any(p.is_file() and p.name != ".keep" for p in media.rglob("*")):
        shutil.copytree(media, target / "media")
    (target / "READ ME.txt").write_text(
        "School office records - backup\r\n"
        f"Made on {timezone.localtime():%d-%m-%Y at %H:%M} ({students} students).\r\n\r\n"
        "To use this backup (only if the records on the computer are lost or damaged):\r\n"
        "1. Close the office system (stop_school.bat).\r\n"
        "2. Copy db.sqlite3 from this folder into the School Office folder, replacing the old one.\r\n"
        "3. If there is a media folder here, copy it there too.\r\n"
        "Ask for help if you are not sure - the current records are replaced by this copy.\r\n",
        encoding="utf-8")
    return target, students


def backup(request):
    school = School.get()
    if request.method == "POST":
        folder = request.POST.get("folder", "").strip().strip('"')
        then_lock = request.POST.get("then_lock") == "1"
        fail_to = "office:closing" if then_lock else "office:settings"
        if not folder:
            messages.error(request, "Choose or type the folder where the backup should be saved.")
            return redirect(fail_to)
        try:
            target, students = make_backup(folder)
        except Exception as e:  # noqa: BLE001 - show the reason in plain words
            messages.error(request, f"The backup could not be saved in “{folder}”: {e}. "
                                    "Check that the USB stick is plugged in, or choose another folder.")
            return redirect(fail_to)
        school.backup_folder = folder
        school.last_backup_at = timezone.now()
        school.save(update_fields=["backup_folder", "last_backup_at"])
        ActivityLog.add("backup", f"Backup saved to {target} ({students} students)")
        if not then_lock:
            messages.success(request, f"Backup saved: {target}  —  {students} students checked in the copy.")
        else:
            from django.contrib.auth import logout
            logout(request)
            messages.success(request, f"Backup saved in {target} ({students} students). The office is locked. Allah Hafiz!")
            return redirect("office:login")
        return redirect(safe_next(request, reverse("office:settings")))
    return redirect("office:settings")


@require_POST
def choose_folder(request):
    """Opens the Windows 'choose folder' window on this computer and returns what was picked."""
    if os.name != "nt":
        return JsonResponse({"folder": "", "error": "Type the folder path in the box."})
    script = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true; $owner.ShowInTaskbar = $false; $owner.StartPosition = 'CenterScreen'
$owner.Size = New-Object System.Drawing.Size(1,1); $owner.Show(); $owner.Activate()
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = 'Choose where to save backups of the school records (a USB stick is best)'
$d.ShowNewFolderButton = $true
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($d.SelectedPath) }
$owner.Close()
"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
                           capture_output=True, timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return JsonResponse({"folder": r.stdout.decode("utf-8", "replace").strip()})
    except Exception:
        return JsonResponse({"folder": "", "error": "The folder window could not open. Type the folder path instead."})


# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------
ICONS = {
    "attendance": "calendar2-check", "login": "person-check", "security": "shield-exclamation",
    "fee": "cash-coin", "student": "person", "class": "grid-3x3-gap", "teacher": "person-badge",
         "salary": "wallet2", "test": "journal-check", "expense": "receipt-cutoff", "certificate": "award",
         "promotion": "arrow-up-circle", "backup": "hdd", "settings": "gear"}


def activity(request):
    qs = ActivityLog.objects.all()
    kind = request.GET.get("kind", "")
    if kind in dict(ActivityLog.KINDS):
        qs = qs.filter(kind=kind)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(text__icontains=q)
    who = request.GET.get("who", "").strip()
    if who:
        qs = qs.filter(who=who)
    page = paginate(request, qs, 100)
    days = []
    for a in page:
        a.icon = ICONS.get(a.kind, "dot")
        d = timezone.localtime(a.at).date()
        if not days or days[-1]["day"] != d:
            days.append({"day": d, "items": []})
        days[-1]["items"].append(a)
    today = timezone.localdate()
    return render(request, "office/activity.html", {
        "page": page, "days": days, "kinds": ActivityLog.KINDS, "kind": kind, "q": q, "today": today, "who": who,
        "staff_names": [n for n in ActivityLog.objects.exclude(who="").values_list("who", flat=True).distinct().order_by("who")],
        "yesterday": today - timezone.timedelta(days=1),
        "today_fees": ActivityLog.objects.filter(kind="fee", at__date=today, amount__isnull=False)
        .aggregate(s=Sum("amount"))["s"] or 0,
    })


# ---------------------------------------------------------------------------
# Other expenses (rent, bills …)
# ---------------------------------------------------------------------------
def expense_list(request):
    month = parse_month(request.GET.get("month"))
    nxt = add_months(month, 1)
    rows = Expense.objects.filter(date__gte=month, date__lt=nxt)
    form = ExpenseForm(request.POST or None, initial={"date": timezone.localdate() if month == timezone.localdate().replace(day=1) else month})
    if request.method == "POST" and form.is_valid():
        e = form.save()
        ActivityLog.add("expense", f"Expense added: {e.category}{' — ' + e.description if e.description else ''}, "
                                   f"Rs. {e.amount:,.0f} on {e.date:%d-%m-%Y}", amount=e.amount,
                        link=f"{reverse('office:expense_list')}?month={e.date:%Y-%m}")
        messages.success(request, f"Saved: {e.category} Rs. {e.amount:,.0f}.")
        return redirect(f"{reverse('office:expense_list')}?month={e.date:%Y-%m}")
    by_cat = rows.values("category").annotate(s=Sum("amount")).order_by("-s")
    return render(request, "office/expenses.html", {
        "month": month, "prev": add_months(month, -1), "next": nxt, "rows": rows, "form": form,
        "total": rows.aggregate(s=Sum("amount"))["s"] or 0, "by_cat": by_cat,
        "school": School.get(),
    })


def expense_edit(request, pk):
    e = get_object_or_404(Expense, pk=pk)
    back = f"{reverse('office:expense_list')}?month={e.date:%Y-%m}"
    form = ExpenseForm(request.POST or None, instance=e)
    if request.method == "POST":
        if "delete" in request.POST:
            e.delete()
            ActivityLog.add("expense", f"Expense deleted: {e.category} Rs. {e.amount:,.0f} of {e.date:%d-%m-%Y}")
            messages.success(request, "Expense deleted.")
            return redirect(back)
        if form.is_valid():
            form.save()
            ActivityLog.add("expense", f"Expense changed: {e.category} Rs. {e.amount:,.0f} on {e.date:%d-%m-%Y}", link=back)
            messages.success(request, "Expense saved.")
            return redirect(back)
    return render(request, "office/expense_edit.html", {"form": form, "e": e, "back": back})


@require_POST
def toggle_expenses(request):
    school = School.get()
    school.show_expenses = request.POST.get("on") == "1"
    school.save(update_fields=["show_expenses"])
    return redirect(safe_next(request, reverse("office:profit")))
