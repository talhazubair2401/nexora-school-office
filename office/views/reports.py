from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone

from ..models import Charge, Expense, Fee, FeePayment, Salary, School, add_months, session_start


def profit(request):
    """Month by month: fee money received minus salaries paid (by the date the money moved)."""
    today = timezone.localdate()
    try:
        start_year = int(request.GET.get("session", ""))
    except ValueError:
        start_year = session_start(today).year
    start = date(start_year, 4, 1)
    end = add_months(start, 12)

    received = dict(FeePayment.objects.filter(paid_on__gte=start, paid_on__lt=end)
                    .annotate(m=TruncMonth("paid_on")).values("m").annotate(s=Sum("amount")).values_list("m", "s"))
    # paper fund and fines paid separately (the ones added to a fee are already in the fee payments)
    for m, amt in (Charge.objects.filter(fee__isnull=True, paid_on__gte=start, paid_on__lt=end)
                   .annotate(m=TruncMonth("paid_on")).values("m").annotate(s=Sum("amount")).values_list("m", "s")):
        received[m] = (received.get(m) or 0) + (amt or 0)
    paid = dict(Salary.objects.filter(paid_on__gte=start, paid_on__lt=end)
                .annotate(m=TruncMonth("paid_on")).values("m").annotate(s=Sum("paid_amount")).values_list("m", "s"))
    show_exp = School.get().show_expenses
    spent = dict(Expense.objects.filter(date__gte=start, date__lt=end)
                 .annotate(m=TruncMonth("date")).values("m").annotate(s=Sum("amount")).values_list("m", "s"))
    spent = {k.replace(day=1) if hasattr(k, "replace") else k: v for k, v in spent.items()}
    received = {k.replace(day=1) if hasattr(k, "replace") else k: v for k, v in received.items()}
    paid = {k.replace(day=1) if hasattr(k, "replace") else k: v for k, v in paid.items()}

    rows = []
    for i in range(12):
        m = add_months(start, i)
        fees = Fee.objects.filter(month=m).prefetch_related("payments")
        billed = sum((f.net for f in fees), Decimal(0))
        r, s = received.get(m, 0) or 0, paid.get(m, 0) or 0
        e = (spent.get(m, 0) or 0) if show_exp else 0
        rows.append({"month": m, "billed": billed, "received": r, "salaries": s, "expenses": e, "profit": r - s - e,
                     "future": m > today.replace(day=1)})
    totals = {k: sum((row[k] for row in rows), Decimal(0)) for k in ("billed", "received", "salaries", "expenses", "profit")}
    first_year = min([d.year for d in FeePayment.objects.dates("paid_on", "year")] + [start_year, today.year - 1])
    sessions = list(range(session_start(today).year, first_year - 1, -1))
    template = "print/profit.html" if request.GET.get("print") else "office/profit.html"
    return render(request, template, {
        "rows": rows, "totals": totals, "start": start, "end": add_months(end, -1), "session": start_year,
        "sessions": sessions, "show_exp": show_exp,
        "chart": {"labels": [r["month"].strftime("%b") for r in rows],
                  "received": [float(r["received"]) for r in rows],
                  "salaries": [float(r["salaries"]) for r in rows],
                  "expenses": [float(r["expenses"]) for r in rows],
                  "profit": [float(r["profit"]) for r in rows]},
    })
