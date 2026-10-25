import csv
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import StudentForm, StudentLeaveForm
from .. import search
from ..access import is_owner
from ..models import ActivityLog, ClassHistory, ClassRoom, Mark, School, Student, Test
from ..results import test_results
from .common import paginate


def _base_qs(request):
    qs = Student.objects.select_related("classroom")
    cls = request.GET.get("class", "")
    status = request.GET.get("status", "ACTIVE")
    if cls.isdigit():
        qs = qs.filter(classroom_id=int(cls))
    if status in Student.Status.values:
        qs = qs.filter(status=status)
    nofee = request.GET.get("nofee") == "1"
    if nofee:
        qs = qs.filter(monthly_fee=0)
    return qs, {"cls": cls, "status": status, "nofee": nofee}


def _filtered(request):
    """Students matching the page's filters, flat list in the chosen order (used by the Excel download)."""
    qs, f = _base_qs(request)
    q = request.GET.get("q", "").strip()
    field = request.GET.get("in", "all")
    groups = search.search(qs, q, field)
    sort = request.GET.get("sort", "name")
    out = []
    for _, _, items in groups:
        out += search.sort_students(items, sort)
    f.update({"q": q, "in": field, "sort": sort})
    return out, f, groups


def student_list(request):
    students, f, groups = _filtered(request)
    sort = f["sort"]
    groups = [(k, title, search.sort_students(items, sort)) for k, title, items in groups]
    page = None
    if not f["q"]:
        page = paginate(request, groups[0][2] if groups else [], 60)
        groups = [("all", "", list(page))]
    params = request.GET.copy()
    for k in ("sort", "page", "partial"):
        params.pop(k, None)
    ctx = {
        "groups": groups, "page": page, "total": len(students), "f": f,
        "classes": ClassRoom.objects.all(), "statuses": Student.Status.choices,
        "fields": search.FIELDS, "sort_qs": params.urlencode(), "numeric": search.is_number_query(f["q"]),
        "columns": [("adm", "Adm. no.", ""), ("name", "Student", ""), ("father", "Father", ""),
                    ("class", "Class", ""), ("roll", "Roll", ""), ("fee", "Monthly fee", "money"),
                    ("phone", "Phone", ""), ("status", "Status", "")],
    }
    if request.GET.get("partial"):
        return render(request, "office/_student_results.html", ctx)
    return render(request, "office/student_list.html", ctx)


def student_suggest(request):
    """Quick results for the search bar at the top (shown while typing)."""
    q = request.GET.get("q", "").strip()
    field = request.GET.get("in", "all")
    out = []
    if q:
        qs = Student.objects.select_related("classroom").exclude(status=Student.Status.LEFT).order_by("name")
        groups = search.search(qs, q, field)
        if not groups:   # look in left / passed-out students too
            groups = search.search(Student.objects.select_related("classroom").order_by("name"), q, field)
        for key, title, items in groups:
            items = search.sort_students(items, "name")
            out.append({"title": title, "more": max(len(items) - 8, 0), "items": [{
                "name": s.name, "father": s.father_name, "adm": s.admission_no, "phone": s.phone,
                "cls": str(s.classroom or ""), "colour": s.classroom.colour if s.classroom else "#999",
                "status": s.get_status_display() if s.status != Student.Status.ACTIVE else "",
                "url": s.get_absolute_url()} for s in items[:8]]})
    return JsonResponse({"q": q, "groups": out})


def student_detail(request, pk):
    s = get_object_or_404(Student.objects.select_related("classroom"), pk=pk)
    fees = list(s.fees.prefetch_related("payments", "charges").order_by("-month"))
    tests = Test.objects.filter(subjects__marks__student=s).distinct().select_related("classroom")
    school = School.get()
    results = []
    for t in tests:
        _, rows = test_results(t, school)
        row = next((r for r in rows if r["student"].pk == s.pk), None)
        if row:
            results.append({"test": t, **row, "out_of": sum(1 for r in rows if r["percent"] is not None)})
    # previous / next student of the same class (same order as the class page)
    prev_s = next_s = None
    pos = count = 0
    if s.classroom_id:
        same = list(Student.objects.filter(classroom_id=s.classroom_id, status=s.status)
                    .order_by("roll_no", "name").values_list("pk", "name"))
        ids = [p for p, _ in same]
        if s.pk in ids:
            i = ids.index(s.pk)
            pos, count = i + 1, len(ids)
            prev_s = same[i - 1] if i > 0 else None
            next_s = same[i + 1] if i + 1 < len(ids) else None
    from .attendance import student_attendance_context
    return render(request, "office/student_detail.html", {
        **student_attendance_context(s),
        "separate_charges": s.charges.filter(fee__isnull=True),
        "separate_unpaid": s.charges.filter(fee__isnull=True, paid_on__isnull=True).exists(),
        "prev_s": prev_s, "next_s": next_s, "pos": pos, "count": count,
        "history": ClassHistory.objects.filter(student=s, batch__undone_at__isnull=True).select_related("batch"),
        "certificates": s.certificates.all()[:20],
        "s": s, "fees": fees, "results": results,
        "balance": sum((f.balance for f in fees), Decimal(0)),
        "paid_total": sum((f.paid for f in fees), Decimal(0)),
        "leave_form": StudentLeaveForm(),
    })


def student_create(request):
    initial = {}
    cls = request.GET.get("class", "")
    if cls.isdigit():
        c = ClassRoom.objects.filter(pk=int(cls)).first()
        if c:
            initial = {"classroom": c, "monthly_fee": c.default_fee,
                       "roll_no": (c.students.order_by("-roll_no").values_list("roll_no", flat=True).first() or 0) + 1}
    locked = not is_owner(request.user)
    form = StudentForm(request.POST or None, request.FILES or None, initial=initial, fee_locked=locked)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        if locked:
            # Office staff: the new student gets the class's usual fee; the owner can change it later.
            s.monthly_fee = s.classroom.default_fee if s.classroom else 0
            s.discount = 0
        s.save()
        ActivityLog.add("student", f"New admission: {s.name} ({s.admission_no}) in {s.classroom}", link=s)
        messages.success(request, f"{s.name} admitted. Admission no. {s.admission_no}.")
        if "add_another" in request.POST:
            return redirect(f"{request.path}?class={s.classroom_id}")
        return redirect(s)
    return render(request, "office/student_form.html", {
        "form": form, "title": "New admission",
        "class_fees": {c.pk: int(c.default_fee) for c in ClassRoom.objects.all()},
        "class_rolls": {c.pk: (c.students.order_by("-roll_no").values_list("roll_no", flat=True).first() or 0) + 1
                        for c in ClassRoom.objects.all()},
    })


def student_update(request, pk):
    s = get_object_or_404(Student, pk=pk)
    old_net = s.net_fee
    form = StudentForm(request.POST or None, request.FILES or None, instance=s,
                       fee_locked=not is_owner(request.user))
    if request.method == "POST" and form.is_valid():
        s = form.save()
        if s.net_fee != old_net:
            messages.info(request, "The new fee is used for months you create from now on. "
                                   "Months already created keep their amount; edit them on the Fees tab if needed.")
        changed = ", ".join(form.fields[n].label or n for n in form.changed_data if n in form.fields)
        ActivityLog.add("student", f"Edited {s.name}'s record" + (f" ({changed})" if changed else ""), link=s)
        messages.success(request, "Student record saved.")
        return redirect(s)
    return render(request, "office/student_form.html", {"form": form, "title": f"Edit {s.name}", "s": s,
                                                        "class_fees": {}, "class_rolls": {}})


@require_POST
def student_leave(request, pk):
    s = get_object_or_404(Student, pk=pk)
    form = StudentLeaveForm(request.POST)
    if form.is_valid():
        s.status = Student.Status.LEFT
        s.left_on = form.cleaned_data["left_on"]
        reason = form.cleaned_data["reason"]
        if reason:
            s.remarks = (s.remarks + "\n" if s.remarks else "") + f"Left on {s.left_on:%d-%m-%Y}: {reason}"
        s.save()
        ActivityLog.add("student", f"{s.name} ({s.classroom}) marked as left school on {s.left_on:%d-%m-%Y}", link=s)
        messages.success(request, f"{s.name} marked as left school. The record and fee history are kept; "
                                  "find it under Students → Left school.")
    return redirect(s)


@require_POST
def student_restore(request, pk):
    s = get_object_or_404(Student, pk=pk)
    s.status = Student.Status.ACTIVE
    s.left_on = None
    s.save()
    ActivityLog.add("student", f"{s.name} brought back to studying", link=s)
    messages.success(request, f"{s.name} is back on the active list.")
    return redirect(s)


def student_delete(request, pk):
    s = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        name = s.name
        adm = s.admission_no
        s.delete()
        ActivityLog.add("student", f"Deleted {name}'s record permanently ({adm})")
        messages.success(request, f"{name}'s record was deleted permanently.")
        return redirect("office:student_list")
    return render(request, "office/confirm.html", {
        "title": f"Delete {s.name} permanently?",
        "message": "This removes the student together with every fee payment, test mark, attendance record and "
                   "paper fund / fine. "
                   "Use this only for a record entered by mistake. When a student leaves, use "
                   "“Mark as left” instead so the history stays.",
        "button": "Delete permanently", "cancel_url": s.get_absolute_url(),
    })


def student_print(request, pk):
    s = get_object_or_404(Student.objects.select_related("classroom"), pk=pk)
    fees = list(s.fees.prefetch_related("payments").order_by("month"))
    return render(request, "print/student_record.html", {
        "s": s, "fees": fees[-12:],
        "balance": sum((f.balance for f in fees), Decimal(0)),
    })


def student_export(request):
    qs, _, _ = _filtered(request)
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="students_{timezone.localdate()}.csv"'
    resp.write("﻿")
    w = csv.writer(resp)
    w.writerow(["Admission no.", "Roll no.", "Name", "Father", "Mother", "Gender", "Date of birth", "B-Form",
                "Father CNIC", "Phone", "Address", "Class", "Admission date", "Monthly fee", "Discount",
                "Net fee", "Status"])
    for s in qs:
        w.writerow([s.admission_no, s.roll_no or "", s.name, s.father_name, s.mother_name, s.get_gender_display(),
                    s.date_of_birth or "", s.b_form_no, s.father_cnic, s.phone, s.address, s.classroom or "",
                    s.admission_date or "", s.monthly_fee, s.discount, s.net_fee, s.get_status_display()])
    return resp
