import os
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from ..forms import SchoolForm
from ..models import (ActivityLog, ClassRoom, Expense, Fee, FeePayment, Salary, School, Student, Teacher, add_months,
                      session_start)


def dashboard(request):
    today = timezone.localdate()
    month = today.replace(day=1)
    next_month = add_months(month, 1)

    classes = ClassRoom.objects.annotate(
        n=Count("students", filter=Q(students__status=Student.Status.ACTIVE)),
    ).order_by("order", "name")
    fees = Fee.objects.filter(month=month).prefetch_related("payments")
    billed = sum((f.net for f in fees), Decimal(0))
    collected_for_month = sum((f.paid for f in fees), Decimal(0))
    unpaid_count = sum(1 for f in fees if f.balance > 0)

    received = FeePayment.objects.filter(paid_on__gte=month, paid_on__lt=next_month).aggregate(s=Sum("amount"))["s"] or 0
    from ..models import Charge
    extra_received = Charge.objects.filter(fee__isnull=True, paid_on__gte=month, paid_on__lt=next_month) \
        .aggregate(s=Sum("amount"))["s"] or 0
    salaries_paid = Salary.objects.filter(paid_on__gte=month, paid_on__lt=next_month).aggregate(s=Sum("paid_amount"))["s"] or 0
    all_balance = sum((f.balance for f in Fee.objects.prefetch_related("payments")), Decimal(0))
    school = School.get()
    expenses = 0
    if school.show_expenses:
        expenses = Expense.objects.filter(date__gte=month, date__lt=next_month).aggregate(s=Sum("amount"))["s"] or 0
    backup_days = (timezone.now() - school.last_backup_at).days if school.last_backup_at else None

    ctx = {
        "today": today, "month": month,
        "classes": classes,
        "student_count": Student.objects.filter(status=Student.Status.ACTIVE).count(),
        "teacher_count": Teacher.objects.filter(status=Teacher.Status.ACTIVE).count(),
        "fees_created": fees.exists(),
        "billed": billed, "collected_for_month": collected_for_month, "unpaid_count": unpaid_count,
        "received": received, "salaries_paid": salaries_paid, "profit": received + extra_received - salaries_paid - expenses, "extra_received": extra_received,
        "expenses": expenses, "show_expenses": school.show_expenses,
        "backup_days": backup_days, "today_received": FeePayment.objects.filter(paid_on=today).aggregate(s=Sum("amount"))["s"] or 0,
        "recent_activity": ActivityLog.objects.all()[:6],
        "all_balance": all_balance,
        "salary_total": Teacher.objects.filter(status=Teacher.Status.ACTIVE).aggregate(s=Sum("salary"))["s"] or 0,
        "recent_payments": FeePayment.objects.select_related("fee__student__classroom")[:8],
        "session_start": session_start(today),
    }
    ctx["att"] = _attendance_today(today)
    return render(request, "office/dashboard.html", ctx)


def _attendance_today(today):
    from ..models import StudentAttendance, TeacherAttendance
    active = Student.objects.filter(status=Student.Status.ACTIVE)
    marks = StudentAttendance.objects.filter(date=today, student__in=active)
    per_class = dict(active.values_list("classroom").annotate(n=Count("id")).values_list("classroom", "n"))
    marked_per_class = dict(marks.values_list("student__classroom").annotate(n=Count("id"))
                            .values_list("student__classroom", "n"))
    t_marks = TeacherAttendance.objects.filter(date=today, teacher__status=Teacher.Status.ACTIVE)
    return {
        "marked": marks.count(), "total": active.count(),
        "present": marks.filter(status__in=["P", "T"]).count(), "absent": marks.filter(status="A").count(),
        "classes": sum(1 for c, n in per_class.items() if c and n),
        "classes_done": sum(1 for c, n in per_class.items() if c and n and marked_per_class.get(c, 0) >= n),
        "teachers_total": Teacher.objects.filter(status=Teacher.Status.ACTIVE).count(),
        "teachers_marked": t_marks.count(), "teachers_present": t_marks.filter(status__in=["P", "T"]).count(),
    }


def school_settings(request):
    school = School.get()
    form = SchoolForm(request.POST or None, request.FILES or None, instance=school)
    if request.method == "POST" and form.is_valid():
        changed = [str(form.fields[n].label or n) for n in form.changed_data]
        form.save()
        if changed:
            ActivityLog.add("settings", "Settings changed: " + ", ".join(changed), link="/settings/")
        messages.success(request, "Settings saved.")
        return redirect("office:settings")
    from .tools import removable_drives
    return render(request, "office/settings.html", {"form": form, "grades": school.grades(), "school": school,
                                                    "drives": removable_drives(), "is_windows": os.name == "nt"})
