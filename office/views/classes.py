from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import ClassRoomForm, SubjectForm
from decimal import Decimal

from ..models import CLASS_COLOURS, ActivityLog, ClassRoom, Fee, Student, Subject


def class_list(request):
    classes = ClassRoom.objects.select_related("class_teacher").annotate(
        n=Count("students", filter=Q(students__status=Student.Status.ACTIVE), distinct=True),
        boys=Count("students", filter=Q(students__status=Student.Status.ACTIVE, students__gender="M"), distinct=True),
        girls=Count("students", filter=Q(students__status=Student.Status.ACTIVE, students__gender="F"), distinct=True),
        n_subjects=Count("subjects", distinct=True),
    ).order_by("order", "name")
    return render(request, "office/class_list.html", {"classes": classes})


def class_detail(request, pk):
    classroom = get_object_or_404(ClassRoom.objects.select_related("class_teacher"), pk=pk)
    month = timezone.localdate().replace(day=1)
    students = list(classroom.active_students.order_by("roll_no", "name"))
    fees = {f.student_id: f for f in Fee.objects.filter(month=month, student__in=students).prefetch_related("payments")}
    rows = [{"s": s, "fee": fees.get(s.pk)} for s in students]
    return render(request, "office/class_detail.html", {
        "classroom": classroom, "rows": rows, "month": month,
        "no_fee": sum(1 for s in students if s.monthly_fee <= 0),
        "subjects": classroom.subjects.all(), "subject_form": SubjectForm(),
        "tests": classroom.tests.all()[:10],
        "others": classroom.students.exclude(status=Student.Status.ACTIVE).count(),
    })


def _next_colour():
    used = set(ClassRoom.objects.values_list("colour", flat=True))
    return next((c for c in CLASS_COLOURS if c not in used), CLASS_COLOURS[0])


def class_create(request):
    initial = {"colour": _next_colour(),
               "order": (ClassRoom.objects.order_by("-order").values_list("order", flat=True).first() or 0) + 1}
    form = ClassRoomForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        ActivityLog.add("class", f"New class added: {c}", link=c)
        messages.success(request, f"{c} added. Now write its subjects.")
        return redirect(c)
    return render(request, "office/class_form.html", {"form": form, "title": "New class"})


def class_update(request, pk):
    classroom = get_object_or_404(ClassRoom, pk=pk)
    form = ClassRoomForm(request.POST or None, instance=classroom)
    if request.method == "POST" and form.is_valid():
        form.save()
        ActivityLog.add("class", f"Class {classroom} edited", link=classroom)
        messages.success(request, "Class saved.")
        return redirect(classroom)
    return render(request, "office/class_form.html", {"form": form, "title": f"Edit {classroom}",
                                                      "classroom": classroom})


def class_delete(request, pk):
    classroom = get_object_or_404(ClassRoom, pk=pk)
    if request.method == "POST":
        if classroom.students.exists():
            messages.error(request, "This class still has students. Move them to another class first.")
            return redirect(classroom)
        classroom.delete()
        ActivityLog.add("class", f"Class {classroom.name} deleted")
        messages.success(request, "Class deleted.")
        return redirect("office:class_list")
    return render(request, "office/confirm.html", {
        "title": f"Delete {classroom}?",
        "message": "Its subjects and tests are deleted too. Classes that still have students can't be deleted.",
        "button": "Delete class", "cancel_url": classroom.get_absolute_url(),
    })


@require_POST
def subject_add(request, pk):
    classroom = get_object_or_404(ClassRoom, pk=pk)
    names = [n.strip() for n in request.POST.get("name", "").split(",") if n.strip()]
    start = classroom.subjects.count()
    added = []
    for i, name in enumerate(names):
        try:
            Subject.objects.create(classroom=classroom, name=name[:60], order=start + i + 1)
            added.append(name)
        except IntegrityError:
            messages.error(request, f"{classroom} already has {name}.")
    if added:
        messages.success(request, f"Added: {', '.join(added)}.")
    return redirect(f"{classroom.get_absolute_url()}#subjects")


@require_POST
def subject_update(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    name = request.POST.get("name", "").strip()[:60]
    if name:
        subject.name = name
        try:
            subject.save()
        except IntegrityError:
            messages.error(request, f"{subject.classroom} already has {name}.")
    return redirect(f"{subject.classroom.get_absolute_url()}#subjects")


@require_POST
def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    classroom = subject.classroom
    subject.delete()
    messages.success(request, f"{subject.name} removed from {classroom}. Old test results keep it.")
    return redirect(f"{classroom.get_absolute_url()}#subjects")


@require_POST
def subject_move(request, pk, direction):
    subject = get_object_or_404(Subject, pk=pk)
    subs = list(subject.classroom.subjects.all())
    i = subs.index(subject)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(subs):
        subs[i], subs[j] = subs[j], subs[i]
        for n, s in enumerate(subs, start=1):
            if s.order != n:
                s.order = n
                s.save(update_fields=["order"])
    return redirect(f"{subject.classroom.get_absolute_url()}#subjects")


@require_POST
def class_apply_fee(request, pk):
    """Give the class's usual fee to its students whose fee isn't set yet."""
    classroom = get_object_or_404(ClassRoom, pk=pk)
    if classroom.default_fee <= 0:
        messages.error(request, "Set the class's usual monthly fee first (Edit class).")
        return redirect(classroom)
    n = classroom.students.filter(monthly_fee=0).update(monthly_fee=classroom.default_fee)
    ActivityLog.add("class", f"{classroom}: usual fee Rs. {classroom.default_fee:,.0f} given to {n} students", link=classroom)
    messages.success(request, f"{n} student{'s' if n != 1 else ''} now have the usual fee of Rs. {classroom.default_fee:,.0f}. "
                              "Check any discounts on their pages.")
    return redirect(classroom)


def class_print_list(request, pk):
    """Printable class list: names, father's names, phone numbers and fees."""
    classroom = get_object_or_404(ClassRoom.objects.select_related("class_teacher"), pk=pk)
    month = timezone.localdate().replace(day=1)
    students = list(classroom.active_students.order_by("roll_no", "name"))
    if request.GET.get("order") == "name":
        students.sort(key=lambda s: s.name.lower())
    fees = list(Fee.objects.filter(student__in=students).prefetch_related("payments"))
    due, this_month = {}, {}
    for f in fees:
        due[f.student_id] = due.get(f.student_id, Decimal(0)) + f.balance
        if f.month == month:
            this_month[f.student_id] = f
    rows = [{"s": s, "due": due.get(s.pk, Decimal(0)), "fee": this_month.get(s.pk)} for s in students]
    show_due = request.GET.get("due", "1") == "1"
    return render(request, "print/class_list.html", {
        "classroom": classroom, "rows": rows, "month": month, "show_due": show_due,
        "order": request.GET.get("order", "roll"),
        "total_fee": sum((s.net_fee for s in students), Decimal(0)),
        "total_due": sum((r["due"] for r in rows), Decimal(0)),
        "boys": sum(1 for s in students if s.gender == "M"), "girls": sum(1 for s in students if s.gender == "F"),
    })
