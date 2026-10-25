from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import SalaryForm, TeacherForm
from ..models import ActivityLog, Salary, Teacher, add_months
from .common import parse_month, safe_next


def teacher_list(request):
    show = request.GET.get("show", "ACTIVE")
    qs = Teacher.objects.all()
    if show in Teacher.Status.values:
        qs = qs.filter(status=show)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(subjects__icontains=q) | Q(cnic__icontains=q))
    return render(request, "office/teacher_list.html", {
        "teachers": qs, "show": show, "q": q,
        "salary_total": sum((t.salary for t in qs if t.status == Teacher.Status.ACTIVE), Decimal(0)),
    })


def teacher_detail(request, pk):
    t = get_object_or_404(Teacher, pk=pk)
    return render(request, "office/teacher_detail.html", {
        "t": t, "salaries": t.salaries.all(), "certificates": t.certificates.all()[:10],
        "classes": t.class_teacher_of.all(),
        "paid_total": sum((s.paid_amount for s in t.salaries.all()), Decimal(0)),
    })


def teacher_create(request):
    form = TeacherForm(request.POST or None, initial={"joining_date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        t = form.save()
        ActivityLog.add("teacher", f"Teacher added: {t.name} (salary Rs. {t.salary:,.0f})", link=t)
        messages.success(request, f"{t.name} added.")
        return redirect(t)
    return render(request, "office/form_page.html", {"form": form, "title": "Add a teacher",
                                                      "cancel": "office:teacher_list", "button": "Save teacher",
                                                      "wide": True})


def teacher_update(request, pk):
    t = get_object_or_404(Teacher, pk=pk)
    form = TeacherForm(request.POST or None, instance=t)
    if request.method == "POST" and form.is_valid():
        t = form.save()
        if t.status == Teacher.Status.LEFT and not t.left_on:
            t.left_on = timezone.localdate()
            t.save(update_fields=["left_on"])
        ActivityLog.add("teacher", f"Teacher record edited: {t.name}", link=t)
        messages.success(request, "Teacher record saved.")
        return redirect(t)
    return render(request, "office/form_page.html", {"form": form, "title": f"Edit {t.name}",
                                                      "cancel": "office:teacher_list", "button": "Save changes",
                                                      "wide": True, "delete_url": reverse("office:teacher_delete", args=[t.pk])})


def teacher_delete(request, pk):
    t = get_object_or_404(Teacher, pk=pk)
    if request.method == "POST":
        t.delete()
        ActivityLog.add("teacher", f"Teacher deleted: {t.name}")
        messages.success(request, f"{t.name} deleted with their salary history.")
        return redirect("office:teacher_list")
    return render(request, "office/confirm.html", {
        "title": f"Delete {t.name} permanently?",
        "message": "Their salary records are deleted too, which changes past profit figures. "
                   "If they stopped working here, set their status to “Left” instead.",
        "button": "Delete permanently", "cancel_url": t.get_absolute_url(),
    })


# ---------------------------------------------------------------------------
# Salaries
# ---------------------------------------------------------------------------
def salary_month(request):
    month = parse_month(request.GET.get("month"))
    rows = Salary.objects.filter(month=month).select_related("teacher").order_by("teacher__name")
    missing = Teacher.objects.filter(status=Teacher.Status.ACTIVE).exclude(salaries__month=month)
    total = sum((r.amount for r in rows), Decimal(0))
    paid = sum((r.paid_amount for r in rows), Decimal(0))
    return render(request, "office/salary_month.html", {
        "month": month, "prev": add_months(month, -1), "next": add_months(month, 1),
        "rows": rows, "missing": missing, "total": total, "paid": paid, "due": total - paid,
    })


@require_POST
def salary_generate(request):
    month = parse_month(request.POST.get("month"))
    n = 0
    with transaction.atomic():
        for t in Teacher.objects.filter(status=Teacher.Status.ACTIVE).exclude(salaries__month=month):
            Salary.objects.create(teacher=t, month=month, amount=t.salary)
            n += 1
    if n:
        ActivityLog.add("salary", f"Salary sheet for {month:%B %Y} created ({n} teachers)",
                        link=f"{reverse('office:salary_month')}?month={month:%Y-%m}")
    messages.success(request, f"Salary sheet for {month:%B %Y} ready ({n} teachers).")
    return redirect(f"{reverse('office:salary_month')}?month={month:%Y-%m}")


@require_POST
def salary_mark_paid(request, pk):
    s = get_object_or_404(Salary.objects.select_related("teacher"), pk=pk)
    s.paid_amount = s.amount
    s.paid_on = timezone.localdate()
    s.save()
    ActivityLog.add("salary", f"Salary paid: {s.teacher.name}, {s.month:%B %Y}", amount=s.paid_amount,
                    link=reverse("office:salary_slip", args=[s.pk]))
    messages.success(request, f"{s.teacher.name}'s salary for {s.month:%B} marked paid.")
    if "print" in request.POST:
        return redirect("office:salary_slip", pk=s.pk)
    return redirect(safe_next(request, f"{reverse('office:salary_month')}?month={s.month:%Y-%m}"))


def salary_edit(request, pk):
    s = get_object_or_404(Salary.objects.select_related("teacher"), pk=pk)
    form = SalaryForm(request.POST or None, instance=s)
    back = safe_next(request, f"{reverse('office:salary_month')}?month={s.month:%Y-%m}")
    if request.method == "POST":
        if "delete" in request.POST:
            s.delete()
            ActivityLog.add("salary", f"{s.month:%B %Y} salary removed for {s.teacher.name}")
            messages.success(request, f"{s.month:%B %Y} salary removed for {s.teacher.name}.")
            return redirect(back)
        if form.is_valid():
            form.save()
            ActivityLog.add("salary", f"Salary changed: {s.teacher.name}, {s.month:%B %Y} — paid Rs. {s.paid_amount:,.0f} "
                                      f"of Rs. {s.amount:,.0f}", link=reverse("office:salary_slip", args=[s.pk]))
            messages.success(request, "Salary saved.")
            return redirect(back)
    return render(request, "office/salary_edit.html", {"form": form, "s": s, "next": back})


def salary_slip(request, pk):
    s = get_object_or_404(Salary.objects.select_related("teacher"), pk=pk)
    return render(request, "print/salary_slip.html", {"s": s, "t": s.teacher})
