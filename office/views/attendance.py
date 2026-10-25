"""Daily attendance for students and teachers, and the monthly registers."""
import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ..access import current_user
from ..models import (ActivityLog, AttendanceStatus, ClassRoom, Student, StudentAttendance, Teacher,
                      TeacherAttendance, session_start)
from .common import parse_month

STUDENT_CHOICES = [("P", "Present"), ("A", "Absent"), ("L", "Leave")]
TEACHER_CHOICES = [("P", "Present"), ("A", "Absent"), ("L", "Leave"), ("T", "Late")]
PRESENT = ("P", "T")   # a late arrival still counts as present


def _day(request):
    """The date being marked: ?date=YYYY-MM-DD, never in the future."""
    today = timezone.localdate()
    try:
        d = date.fromisoformat(request.POST.get("date") or request.GET.get("date", ""))
    except ValueError:
        d = today
    return min(d, today)


def summarise(statuses):
    """Counts and percentage from a list of status letters."""
    c = Counter(statuses)
    marked = sum(c.values())
    present = c["P"] + c["T"]
    return {"present": present, "absent": c["A"], "leave": c["L"], "late": c["T"], "marked": marked,
            "percent": round(present * 100 / marked) if marked else None}


def student_summary(student, start, end):
    return summarise(StudentAttendance.objects.filter(student=student, date__gte=start, date__lte=end)
                     .values_list("status", flat=True))


def student_attendance_context(student):
    """Used on the student's page: this month and this school year."""
    today = timezone.localdate()
    return {"att_month": student_summary(student, today.replace(day=1), today),
            "att_session": student_summary(student, session_start(today), today)}


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
def attendance_home(request):
    day = _day(request)
    today = timezone.localdate()
    marks = (StudentAttendance.objects.filter(date=day, student__status=Student.Status.ACTIVE)
             .values("student__classroom").annotate(n=Count("id"), absent=Count("id", filter=Q(status="A")),
                                                    leave=Count("id", filter=Q(status="L"))))
    by_class = {m["student__classroom"]: m for m in marks}
    classes = []
    for c in ClassRoom.objects.annotate(
            total=Count("students", filter=Q(students__status=Student.Status.ACTIVE))).order_by("order", "name"):
        m = by_class.get(c.pk, {})
        n = m.get("n", 0)
        classes.append({"c": c, "total": c.total, "marked": n, "absent": m.get("absent", 0), "leave": m.get("leave", 0),
                        "present": n - m.get("absent", 0) - m.get("leave", 0), "done": n and n >= c.total})
    absent = (StudentAttendance.objects.filter(date=day, status__in=["A", "L"], student__status=Student.Status.ACTIVE)
              .select_related("student__classroom").order_by("student__classroom__order", "student__name"))
    teachers = TeacherAttendance.objects.filter(date=day, teacher__status=Teacher.Status.ACTIVE)
    t_counts = Counter(teachers.values_list("status", flat=True))
    return render(request, "office/attendance_home.html", {
        "day": day, "today": today, "is_today": day == today, "is_sunday": day.weekday() == 6,
        "prev_day": day - timedelta(days=1), "next_day": day + timedelta(days=1) if day < today else None,
        "classes": classes, "absent": absent,
        "classes_done": sum(1 for x in classes if x["done"]), "classes_with_students": sum(1 for x in classes if x["total"]),
        "students_present": sum(x["present"] for x in classes), "students_total": sum(x["total"] for x in classes),
        "teachers_total": Teacher.objects.filter(status=Teacher.Status.ACTIVE).count(),
        "teachers_marked": sum(t_counts.values()), "teachers_present": t_counts["P"] + t_counts["T"],
        "teachers_away": teachers.filter(status__in=["A", "L"]).select_related("teacher"),
    })


def attendance_mark(request, pk):
    c = get_object_or_404(ClassRoom, pk=pk)
    day = _day(request)
    students = list(c.students.filter(status=Student.Status.ACTIVE).order_by("roll_no", "name"))
    existing = {a.student_id: a.status for a in StudentAttendance.objects.filter(date=day, student__in=students)}
    if request.method == "POST":
        user = current_user()
        counts = Counter()
        with transaction.atomic():
            for s in students:
                status = request.POST.get(f"s{s.pk}", "P")
                if status not in dict(STUDENT_CHOICES):
                    status = "P"
                counts[status] += 1
                StudentAttendance.objects.update_or_create(student=s, date=day,
                                                           defaults={"status": status, "marked_by": user})
        again = " (changed)" if existing else ""
        ActivityLog.add("attendance", f"{c.name} attendance for {day:%d %b %Y}{again}: {counts['P']} present, "
                                      f"{counts['A']} absent, {counts['L']} on leave",
                        link=f"{reverse('office:attendance_mark', args=[c.pk])}?date={day:%Y-%m-%d}")
        messages.success(request, f"{c.name} attendance saved: {counts['P']} present, {counts['A']} absent, "
                                  f"{counts['L']} on leave.")
        return redirect(f"{reverse('office:attendance_home')}?date={day:%Y-%m-%d}")
    rows = [{"s": s, "status": existing.get(s.pk, "P")} for s in students]
    counts = Counter(r["status"] for r in rows)
    return render(request, "office/attendance_mark.html", {
        "c": c, "day": day, "rows": rows, "choices": STUDENT_CHOICES, "already": bool(existing),
        "counts": counts, "is_sunday": day.weekday() == 6, "today": timezone.localdate(),
        "all_classes": ClassRoom.objects.order_by("order", "name"),
    })


def _month_grid(month, people, records, today):
    """Rows of a register: one cell per day of the month."""
    n_days = calendar.monthrange(month.year, month.month)[1]
    days = [month.replace(day=d) for d in range(1, n_days + 1)]
    by_person = defaultdict(dict)
    for pid, d, status in records:
        by_person[pid][d] = status
    rows = []
    for p in people:
        marks = by_person.get(p.pk, {})
        cells = []
        for d in days:
            st = marks.get(d, "")
            cells.append({"s": st, "sun": d.weekday() == 6, "future": d > today})
        rows.append({"p": p, "cells": cells, **summarise(list(marks.values()))})
    return days, rows


def attendance_register(request, pk):
    c = get_object_or_404(ClassRoom, pk=pk)
    month = parse_month(request.GET.get("month"))
    today = timezone.localdate()
    end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    students = list(c.students.filter(Q(status=Student.Status.ACTIVE) | Q(attendance__date__gte=month,
                                                                          attendance__date__lte=end))
                    .distinct().order_by("roll_no", "name"))
    records = StudentAttendance.objects.filter(student__in=students, date__gte=month, date__lte=end) \
        .values_list("student_id", "date", "status")
    days, rows = _month_grid(month, students, records, today)
    ctx = {"c": c, "month": month, "days": days, "rows": rows, "today": today,
           "all_classes": ClassRoom.objects.order_by("order", "name"),
           "prev": (month - timedelta(days=1)).replace(day=1), "next": end + timedelta(days=1)}
    if request.GET.get("print"):
        return render(request, "print/attendance_register.html", ctx)
    return render(request, "office/attendance_register.html", ctx)


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------
def teacher_attendance(request):
    day = _day(request)
    today = timezone.localdate()
    teachers = list(Teacher.objects.filter(status=Teacher.Status.ACTIVE).order_by("name"))
    existing = {a.teacher_id: a for a in TeacherAttendance.objects.filter(date=day, teacher__in=teachers)}
    if request.method == "POST":
        user = current_user()
        counts = Counter()
        with transaction.atomic():
            for t in teachers:
                status = request.POST.get(f"t{t.pk}", "P")
                if status not in dict(TEACHER_CHOICES):
                    status = "P"
                counts[status] += 1
                TeacherAttendance.objects.update_or_create(
                    teacher=t, date=day, defaults={"status": status, "marked_by": user,
                                                   "note": request.POST.get(f"n{t.pk}", "")[:120]})
        late = f" ({counts['T']} late)" if counts["T"] else ""
        ActivityLog.add("attendance", f"Teacher attendance for {day:%d %b %Y}: {counts['P'] + counts['T']} present"
                                      f"{late}, {counts['A']} absent, {counts['L']} on leave",
                        link=f"{reverse('office:teacher_attendance')}?date={day:%Y-%m-%d}")
        messages.success(request, "Teacher attendance saved.")
        return redirect(f"{reverse('office:teacher_attendance')}?date={day:%Y-%m-%d}")
    month = day.replace(day=1)
    month_counts = defaultdict(list)
    for tid, st in TeacherAttendance.objects.filter(date__gte=month, date__lte=day).values_list("teacher_id", "status"):
        month_counts[tid].append(st)
    rows = []
    for t in teachers:
        a = existing.get(t.pk)
        rows.append({"t": t, "status": a.status if a else "P", "note": a.note if a else "",
                     "month": summarise(month_counts.get(t.pk, []))})
    return render(request, "office/teacher_attendance.html", {
        "day": day, "today": today, "rows": rows, "choices": TEACHER_CHOICES, "already": bool(existing),
        "prev_day": day - timedelta(days=1), "next_day": day + timedelta(days=1) if day < today else None,
        "is_sunday": day.weekday() == 6, "month": month,
    })


def teacher_attendance_month(request):
    month = parse_month(request.GET.get("month"))
    today = timezone.localdate()
    end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    teachers = list(Teacher.objects.filter(Q(status=Teacher.Status.ACTIVE) | Q(attendance__date__gte=month,
                                                                              attendance__date__lte=end))
                    .distinct().order_by("name"))
    records = TeacherAttendance.objects.filter(teacher__in=teachers, date__gte=month, date__lte=end) \
        .values_list("teacher_id", "date", "status")
    days, rows = _month_grid(month, teachers, records, today)
    ctx = {"month": month, "days": days, "rows": rows, "today": today, "teachers": True,
           "prev": (month - timedelta(days=1)).replace(day=1), "next": end + timedelta(days=1)}
    if request.GET.get("print"):
        return render(request, "print/attendance_register.html", ctx)
    return render(request, "office/teacher_attendance_month.html", ctx)


STATUS_LABELS = dict(AttendanceStatus.choices)
