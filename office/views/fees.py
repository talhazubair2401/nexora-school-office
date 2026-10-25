from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import AddFeeMonthForm, FeeEditForm, PaymentForm
from ..access import is_owner
from ..models import ActivityLog, Charge, ClassRoom, Fee, FeePayment, School, Student, add_months
from .common import parse_month, safe_next


def _arrears_before(month, student_ids):
    """Unpaid balance of earlier months, per student."""
    out = defaultdict(Decimal)
    for f in Fee.objects.filter(student_id__in=student_ids, month__lt=month).prefetch_related("payments"):
        out[f.student_id] += f.balance
    return out


def _month_rows(month, cls="", status="", q=""):
    fees = Fee.objects.filter(month=month).select_related("student__classroom").prefetch_related("payments")
    if cls.isdigit():
        fees = fees.filter(student__classroom_id=int(cls))
    if q:
        fees = fees.filter(Q(student__name__icontains=q) | Q(student__father_name__icontains=q)
                           | Q(student__admission_no__icontains=q))
    fees = sorted(fees, key=lambda f: (f.student.classroom.order if f.student.classroom else 99,
                                       f.student.roll_no or 0, f.student.name))
    arrears = _arrears_before(month, [f.student_id for f in fees])
    rows = [{"fee": f, "arrears": arrears.get(f.student_id, Decimal(0))} for f in fees]
    if status == "unpaid":
        rows = [r for r in rows if r["fee"].balance > 0 or r["arrears"] > 0]
    elif status == "paid":
        rows = [r for r in rows if r["fee"].balance == 0]
    return rows


def fee_month(request):
    month = parse_month(request.GET.get("month"))
    cls, status, q = request.GET.get("class", ""), request.GET.get("status", ""), request.GET.get("q", "").strip()
    rows = _month_rows(month, cls, status, q)
    totals = {
        "net": sum((r["fee"].net for r in rows), Decimal(0)),
        "paid": sum((r["fee"].paid for r in rows), Decimal(0)),
        "balance": sum((r["fee"].balance for r in rows), Decimal(0)),
        "arrears": sum((r["arrears"] for r in rows), Decimal(0)),
    }
    without = Student.objects.filter(status=Student.Status.ACTIVE).exclude(fees__month=month)
    return render(request, "office/fee_month.html", {
        "month": month, "prev": add_months(month, -1), "next": add_months(month, 1),
        "rows": rows, "totals": totals, "cls": cls, "status": status, "q": q,
        "classes": ClassRoom.objects.all(),
        "missing": without.count(), "missing_zero": without.filter(monthly_fee=0).count(),
        "month_exists": Fee.objects.filter(month=month).exists(),
    })


@require_POST
def fee_generate(request):
    month = parse_month(request.POST.get("month"))
    students = Student.objects.filter(status=Student.Status.ACTIVE).exclude(fees__month=month)
    created, skipped = 0, []
    with transaction.atomic():
        for s in students:
            if s.monthly_fee <= 0:
                skipped.append(s.name)
                continue
            Fee.objects.create(student=s, month=month, amount=s.monthly_fee, discount=s.discount)
            created += 1
    if created:
        ActivityLog.add("fee", f"Created {month:%B %Y} fees for {created} students",
                        link=f"{reverse('office:fee_month')}?month={month:%Y-%m}")
    messages.success(request, f"Fees for {month:%B %Y} created for {created} students.")
    if skipped:
        messages.warning(request, f"{len(skipped)} students have no monthly fee set, so no fee was created for them: "
                                  f"{', '.join(skipped[:12])}{'…' if len(skipped) > 12 else ''}. "
                                  "Set their fee on the student page, then press the button again.")
    return redirect(f"{reverse('office:fee_month')}?month={month:%Y-%m}")


@require_POST
def fee_add_for_student(request, pk):
    s = get_object_or_404(Student, pk=pk)
    form = AddFeeMonthForm(request.POST)
    if form.is_valid():
        month = form.cleaned_data["month"]
        fee, created = Fee.objects.get_or_create(student=s, month=month,
                                                 defaults={"amount": s.monthly_fee, "discount": s.discount})
        if created:
            ActivityLog.add("fee", f"Added {month:%B %Y} fee (Rs. {fee.net:,.0f}) for {s.name}", link=s)
            messages.success(request, f"Fee for {month:%B %Y} added: {fee.net:,.0f}.")
        else:
            messages.info(request, f"{month:%B %Y} was already there.")
    return redirect(f"{s.get_absolute_url()}#fees")


def fee_edit(request, pk):
    fee = get_object_or_404(Fee.objects.select_related("student"), pk=pk)
    form = FeeEditForm(request.POST or None, instance=fee)
    if request.method == "POST" and form.is_valid():
        form.save()
        ActivityLog.add("fee", f"Changed {fee.student.name}'s {fee.month:%B %Y} fee to Rs. {fee.net:,.0f}", link=fee.student)
        messages.success(request, f"{fee.student.name}'s fee for {fee.month:%B %Y} is now Rs. {fee.net:,.0f}.")
        return redirect(safe_next(request, fee.student.get_absolute_url()))
    return render(request, "office/fee_edit.html", {"form": form, "fee": fee,
                                                    "next": request.GET.get("next", "")})


def fee_delete(request, pk):
    fee = get_object_or_404(Fee.objects.select_related("student"), pk=pk)
    back = safe_next(request, fee.student.get_absolute_url())
    if request.method == "POST":
        if fee.payments.exists():
            messages.error(request, "This month has payments. Delete the payments first.")
        else:
            fee.delete()
            ActivityLog.add("fee", f"Removed {fee.month:%B %Y} fee from {fee.student.name}", link=fee.student)
            messages.success(request, f"{fee.month:%B %Y} removed from {fee.student.name}'s fees.")
        return redirect(back)
    return render(request, "office/confirm.html", {
        "title": f"Remove {fee.month:%B %Y} fee for {fee.student.name}?",
        "message": "Use this if the student shouldn't be charged for this month at all.",
        "button": "Remove this month", "cancel_url": back, "next": back,
    })


def payment_add(request, pk):
    fee = get_object_or_404(Fee.objects.select_related("student__classroom").prefetch_related("payments"), pk=pk)
    form = PaymentForm(request.POST or None, balance=fee.balance, lock_date=not is_owner(request.user),
                       initial={"amount": fee.balance, "paid_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.fee = fee
        p.save()
        ActivityLog.add("fee", f"Received Rs. {p.amount:,.0f} from {fee.student.name} ({fee.student.classroom or 'no class'}) "
                               f"for {fee.month:%B %Y} — part payment, receipt {p.receipt_no}",
                        amount=p.amount, link=reverse("office:receipt", args=[p.pk]))
        messages.success(request, f"Received Rs. {p.amount:,.0f} from {fee.student.name}. Receipt {p.receipt_no}.")
        if "print" in request.POST:
            return redirect("office:receipt", pk=p.pk)
        return redirect(safe_next(request, fee.student.get_absolute_url()))
    return render(request, "office/payment_form.html", {"form": form, "fee": fee,
                                                        "next": request.GET.get("next", "")})


@require_POST
def fee_mark_paid(request, pk):
    """One click: receive the whole balance today."""
    fee = get_object_or_404(Fee.objects.select_related("student__classroom").prefetch_related("payments"), pk=pk)
    if fee.balance > 0:
        p = FeePayment.objects.create(fee=fee, amount=fee.balance, paid_on=timezone.localdate())
        ActivityLog.add("fee", f"Received Rs. {p.amount:,.0f} from {fee.student.name} ({fee.student.classroom or 'no class'}) "
                               f"for {fee.month:%B %Y} — paid in full, receipt {p.receipt_no}",
                        amount=p.amount, link=reverse("office:receipt", args=[p.pk]))
        messages.success(request, f"{fee.student.name}: {fee.month:%B} marked paid (Rs. {p.amount:,.0f}, receipt {p.receipt_no}).")
    return redirect(safe_next(request, reverse("office:fee_month")))


def payment_delete(request, pk):
    p = get_object_or_404(FeePayment.objects.select_related("fee__student"), pk=pk)
    back = safe_next(request, p.fee.student.get_absolute_url())
    if request.method == "POST":
        p.delete()
        ActivityLog.add("fee", f"Deleted payment {p.receipt_no} (Rs. {p.amount:,.0f}) of {p.fee.student.name} "
                               f"for {p.fee.month:%B %Y}", link=p.fee.student)
        messages.success(request, f"Payment {p.receipt_no} deleted.")
        return redirect(back)
    return render(request, "office/confirm.html", {
        "title": f"Delete payment {p.receipt_no}?",
        "message": f"Rs. {p.amount:,.0f} received on {p.paid_on:%d-%m-%Y} for {p.fee.month:%B %Y} will be removed, "
                   "and that month will show as due again.",
        "button": "Delete payment", "cancel_url": back, "next": back,
    })


# ---------------------------------------------------------------------------
# Printouts
# ---------------------------------------------------------------------------
def receipt(request, pk):
    p = get_object_or_404(FeePayment.objects.select_related("fee__student__classroom"), pk=pk)
    fee = Fee.objects.prefetch_related("payments").get(pk=p.fee_id)
    still_due = p.fee.student.balance_due()
    return render(request, "print/receipt.html", {"p": p, "fee": fee, "s": fee.student, "still_due": still_due})


def _challan_ctx(student, school):
    unpaid = student.unpaid_fees()
    today = timezone.localdate()
    due_day = min(school.fee_due_day, 28)
    last_date = today.replace(day=due_day) if today.day <= due_day else add_months(today, 1).replace(day=due_day)
    return {"s": student, "unpaid": unpaid, "total": sum((f.balance for f in unpaid), Decimal(0)),
            "last_date": last_date, "issued": today}


def challan(request, pk):
    s = get_object_or_404(Student.objects.select_related("classroom"), pk=pk)
    return render(request, "print/challan.html", {"challans": [_challan_ctx(s, School.get())]})


def class_challans(request):
    """Fee challans for every student who owes money (optionally one class), ready to print."""
    cls = request.GET.get("class", "")
    school = School.get()
    students = Student.objects.filter(status=Student.Status.ACTIVE).select_related("classroom")
    if cls.isdigit():
        students = students.filter(classroom_id=int(cls))
    challans = [c for c in (_challan_ctx(s, school) for s in students) if c["total"] > 0]
    if not challans:
        messages.info(request, "Nobody owes any fee for this selection.")
        return redirect(safe_next(request, reverse("office:fee_month")))
    return render(request, "print/challan.html", {"challans": challans})


def unpaid_list(request):
    month = parse_month(request.GET.get("month"))
    cls = request.GET.get("class", "")
    rows = _month_rows(month, cls, "unpaid")
    classroom = ClassRoom.objects.filter(pk=int(cls)).first() if cls.isdigit() else None
    return render(request, "print/unpaid_list.html", {
        "month": month, "rows": rows, "classroom": classroom,
        "total": sum((r["fee"].balance + r["arrears"] for r in rows), Decimal(0)),
    })


# ---------------------------------------------------------------------------
# Daily collection report
# ---------------------------------------------------------------------------
def daily_collection(request):
    """Money received each day (by the date it was received), with totals."""
    from datetime import date as _date, timedelta

    today = timezone.localdate()
    try:
        start = _date.fromisoformat(request.GET.get("from", ""))
    except ValueError:
        start = today.replace(day=1)
    try:
        end = _date.fromisoformat(request.GET.get("to", ""))
    except ValueError:
        end = today
    if end < start:
        start, end = end, start
    cls = request.GET.get("class", "")
    pays = (FeePayment.objects.filter(paid_on__gte=start, paid_on__lte=end)
            .select_related("fee__student__classroom", "received_by").order_by("paid_on", "receipt_no"))
    if cls.isdigit():
        pays = pays.filter(fee__student__classroom_id=int(cls))
    by_day = defaultdict(list)
    for p in pays:
        by_day[p.paid_on].append(p)
    show_empty = request.GET.get("empty") == "1"
    days, running, d = [], Decimal(0), start
    while d <= end:
        items = by_day.get(d, [])
        total = sum((p.amount for p in items), Decimal(0))
        running += total
        if items or show_empty:
            days.append({"day": d, "items": items, "total": total, "count": len(items), "running": running})
        d += timedelta(days=1)
    grand = running
    n_days = sum(1 for x in days if x["count"])
    # Today's cash check: what each person received today, to count against the cash drawer.
    by_person = defaultdict(lambda: {"total": Decimal(0), "count": 0})
    for p in FeePayment.objects.filter(paid_on=today).select_related("received_by"):
        row = by_person[p.received_by_name or "Principal"]
        row["total"] += p.amount
        row["count"] += 1
    for c in Charge.objects.filter(paid_on=today, fee__isnull=True).select_related("received_by"):
        row = by_person[c.received_by_name or "Principal"]
        row["total"] += c.amount
        row["count"] += 1
    cash_today = sorted(({"name": k, **v} for k, v in by_person.items()), key=lambda r: -r["total"])
    template = "print/daily_collection.html" if request.GET.get("print") else "office/daily_collection.html"
    params = request.GET.copy()
    params.pop("print", None)
    return render(request, template, {
        "charges_total": Charge.objects.filter(fee__isnull=True, paid_on__gte=start, paid_on__lte=end)
                         .aggregate(s=Sum("amount"))["s"] or 0,
        "charges": Charge.objects.filter(fee__isnull=True, paid_on__gte=start, paid_on__lte=end)
                   .select_related("student__classroom", "received_by").order_by("paid_on", "receipt_no"),
        "cash_today": cash_today, "cash_today_total": sum((r["total"] for r in cash_today), Decimal(0)),
        "days": days, "start": start, "end": end, "grand": grand, "count": sum(x["count"] for x in days),
        "n_days": n_days, "average": (grand / n_days) if n_days else 0, "cls": cls, "show_empty": show_empty,
        "classroom": ClassRoom.objects.filter(pk=int(cls)).first() if cls.isdigit() else None,
        "classes": ClassRoom.objects.all(), "today": today, "qs": params.urlencode(),
        "best": max(days, key=lambda x: x["total"]) if days else None,
        "quick": [("Today", today, today), ("Yesterday", today - timedelta(days=1), today - timedelta(days=1)),
                  ("This month", today.replace(day=1), today),
                  ("Last month", add_months(today.replace(day=1), -1), today.replace(day=1) - timedelta(days=1))],
    })
