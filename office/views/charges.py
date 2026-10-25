"""Paper fund and fines: added to a month's fee, or kept separate with their own slip and receipt."""
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..access import current_user
from ..forms import ChargeForm
from ..models import ActivityLog, Charge, ClassRoom, Fee, School, Student, month_start
from .common import paginate, safe_next


def _filtered(request):
    qs = Charge.objects.select_related("student__classroom", "fee", "received_by")
    kind, status, cls = request.GET.get("kind", ""), request.GET.get("status", ""), request.GET.get("class", "")
    if kind in Charge.Kind.values:
        qs = qs.filter(kind=kind)
    if cls.isdigit():
        qs = qs.filter(student__classroom_id=int(cls))
    if status == "unpaid":
        qs = qs.filter(fee__isnull=True, paid_on__isnull=True)
    elif status == "paid":
        qs = qs.filter(fee__isnull=True, paid_on__isnull=False)
    elif status == "withfee":
        qs = qs.filter(fee__isnull=False)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(student__name__icontains=q) | Q(reason__icontains=q) | Q(receipt_no__icontains=q))
    batch = request.GET.get("batch", "").strip()
    if batch:
        qs = qs.filter(batch=batch)
    return qs, {"kind": kind, "status": status, "cls": cls, "q": q, "batch": batch}


def charge_list(request):
    qs, f = _filtered(request)
    separate_unpaid = qs.filter(fee__isnull=True, paid_on__isnull=True)
    page = paginate(request, qs, 100)
    groups = _groups(qs)
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "office/charge_list.html", {
        "page": page, **f, "kinds": Charge.Kind.choices, "classes": ClassRoom.objects.order_by("order", "name"),
        "total": qs.aggregate(s=Sum("amount"))["s"] or 0,
        "unpaid_total": separate_unpaid.aggregate(s=Sum("amount"))["s"] or 0,
        "unpaid_count": separate_unpaid.count(),
        "received_total": qs.filter(fee__isnull=True, paid_on__isnull=False).aggregate(s=Sum("amount"))["s"] or 0,
        "withfee_total": qs.filter(fee__isnull=False).aggregate(s=Sum("amount"))["s"] or 0,
        "qs": params.urlencode(), "groups": groups,
    })


def charge_add(request):
    initial = {}
    for key in ("student", "kind", "how"):
        if request.GET.get(key):
            initial[key] = request.GET[key]
    if request.GET.get("class"):
        initial.update({"who": "class", "classroom": request.GET["class"]})
    if request.GET.get("month"):
        from .common import parse_month
        initial["month"] = parse_month(request.GET["month"])
        initial.setdefault("how", "fee")
    form = ChargeForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        students = [d["student"]] if d["who"] == "student" else \
            list(d["classroom"].students.filter(status=Student.Status.ACTIVE).order_by("roll_no", "name"))
        if not students:
            messages.warning(request, "There are no studying students in that class.")
            return redirect(request.get_full_path())
        month = month_start(d["month"]) if d["how"] == "fee" else None
        user, made_fees = current_user(), 0
        import uuid
        batch = uuid.uuid4().hex if d["who"] == "class" else ""
        batch_label = str(d["classroom"])[:80] if d["who"] == "class" else ""
        with transaction.atomic():
            for s in students:
                fee = None
                if month:
                    fee, created = Fee.objects.get_or_create(student=s, month=month,
                                                             defaults={"amount": s.monthly_fee, "discount": s.discount})
                    made_fees += created
                Charge.objects.create(student=s, kind=d["kind"], amount=d["amount"], reason=d["reason"], date=d["date"],
                                      fee=fee, created_by=user, batch=batch, batch_label=batch_label)
                if fee:
                    fee.refresh_extra()
        what = dict(Charge.Kind.choices)[d["kind"]] + (f" ({d['reason']})" if d["reason"] else "")
        who = students[0].name if d["who"] == "student" else f"{len(students)} students of {d['classroom']}"
        where = f"added to the {month:%B %Y} fee" if month else "on a separate slip"
        ActivityLog.add("fee", f"{what} Rs. {d['amount']:,} for {who}, {where}",
                        link=students[0] if d["who"] == "student" else reverse("office:charge_list"))
        messages.success(request, f"{what} of Rs. {d['amount']:,} added for {who}, {where}."
                         + (f" ({made_fees} {month:%B} fee{'s' if made_fees != 1 else ''} made as well.)" if made_fees else ""))
        if d["who"] == "student":
            return redirect(f"{students[0].get_absolute_url()}#fees")
        return redirect(f"{reverse('office:charge_list')}?class={d['classroom'].pk}")
    student = None
    if str(initial.get("student", "")).isdigit():
        student = Student.objects.filter(pk=int(initial["student"])).first()
    return render(request, "office/charge_form.html", {"form": form, "student": student})


@require_POST
def charge_receive(request, pk):
    c = get_object_or_404(Charge.objects.select_related("student__classroom"), pk=pk)
    if c.with_fee:
        messages.info(request, "This was added to a month's fee. Receive it with the fee.")
        return redirect(safe_next(request, c.student.get_absolute_url()))
    if not c.paid_on:
        c.receive()
        ActivityLog.add("fee", f"Received Rs. {c.amount:,.0f} {c.label.lower()} from {c.student.name} "
                               f"({c.student.classroom or 'no class'}), receipt {c.receipt_no}",
                        amount=c.amount, link=reverse("office:charge_receipt", args=[c.pk]))
        messages.success(request, f"Received Rs. {c.amount:,.0f} from {c.student.name}. Receipt {c.receipt_no}.")
    if "print" in request.POST:
        return redirect("office:charge_receipt", pk=c.pk)
    return redirect(safe_next(request, reverse("office:charge_list")))


def charge_receipt(request, pk):
    c = get_object_or_404(Charge.objects.select_related("student__classroom"), pk=pk, paid_on__isnull=False)
    return render(request, "print/charge_receipt.html", {"c": c, "s": c.student})


def charge_slips(request):
    """Slips to send home for separate (not with fee) unpaid paper fund / fines. One per student."""
    qs, _ = _filtered(request)
    qs = qs.filter(fee__isnull=True, paid_on__isnull=True)
    if request.GET.get("student", "").isdigit():
        qs = qs.filter(student_id=int(request.GET["student"]))
    by_student = {}
    for c in qs.order_by("student__classroom__order", "student__name", "date"):
        by_student.setdefault(c.student, []).append(c)
    if not by_student:
        messages.info(request, "Nothing separate is waiting to be paid for this selection.")
        return redirect(safe_next(request, reverse("office:charge_list")))
    school = School.get()
    today = timezone.localdate()
    slips = [{"s": s, "items": items, "total": sum((i.amount for i in items), Decimal(0))} for s, items in by_student.items()]
    return render(request, "print/charge_slips.html", {"slips": slips, "issued": today, "school": school})


def charge_delete(request, pk):
    c = get_object_or_404(Charge.objects.select_related("student", "fee"), pk=pk)
    back = safe_next(request, reverse("office:charge_list"))
    if request.method == "POST":
        fee = c.fee
        if fee and fee.paid >= fee.net:
            messages.warning(request, f"The {fee.month:%B %Y} fee was already paid including this amount. "
                                      "If the money was given back, also correct the payment on the student's page.")
        text = f"Removed {c.label.lower()} Rs. {c.amount:,.0f} from {c.student.name}" + \
               (f" (receipt {c.receipt_no} cancelled)" if c.receipt_no else "")
        c.delete()
        if fee:
            fee.refresh_extra()
        ActivityLog.add("fee", text, link=c.student)
        messages.success(request, text + ".")
        return redirect(back)
    return render(request, "office/confirm.html", {
        "title": f"Remove this {c.get_kind_display().lower()}?", "next": back, "cancel_url": back,
        "message": f"{c.label} of Rs. {c.amount:,.0f} for {c.student.name}"
                + (f", added to the {c.fee.month:%B %Y} fee" if c.fee else "")
                + (f". It was already paid (receipt {c.receipt_no}); removing it also removes that money from the records."
                   if c.receipt_no else "."),
        "button": "Yes, remove it"})


# ---------------------------------------------------------------------------
# Added together (e.g. paper fund for a whole class): see and remove as one
# ---------------------------------------------------------------------------
def _is_settled(c):
    """Already paid: a separate one with a receipt, or one added to a fee that is fully paid."""
    if c.fee_id:
        return c.fee.balance <= 0
    return bool(c.paid_on)


def _groups(qs):
    groups = {}
    for c in qs.exclude(batch="").select_related("fee").prefetch_related("fee__payments"):
        g = groups.setdefault(c.batch, {"batch": c.batch, "label": c.batch_label, "kind": c.get_kind_display(),
                                        "reason": c.reason, "amount": c.amount, "date": c.date,
                                        "month": c.fee.month if c.fee_id else None, "count": 0, "total": 0,
                                        "settled": 0})
        g["count"] += 1
        g["total"] += c.amount
        g["settled"] += _is_settled(c)
    return sorted(groups.values(), key=lambda g: g["date"], reverse=True)


def charge_batch_delete(request, batch):
    items = list(Charge.objects.filter(batch=batch).select_related("student", "fee").prefetch_related("fee__payments"))
    if not items:
        messages.info(request, "Those were already removed.")
        return redirect("office:charge_list")
    first = items[0]
    what = first.get_kind_display() + (f" ({first.reason})" if first.reason else "")
    settled = [c for c in items if _is_settled(c)]
    back = reverse("office:charge_list")
    if request.method == "POST":
        remove = items if request.POST.get("mode") == "all" else [c for c in items if not _is_settled(c)]
        fees = {c.fee for c in remove if c.fee_id}
        with transaction.atomic():
            Charge.objects.filter(pk__in=[c.pk for c in remove]).delete()
            for f in fees:
                f.refresh_extra()
        kept = len(items) - len(remove)
        ActivityLog.add("fee", f"Removed {what} Rs. {first.amount:,.0f} from {len(remove)} students"
                               f"{f' of {first.batch_label}' if first.batch_label else ''}"
                               f"{f' (kept {kept} already paid)' if kept else ''}", link=back)
        msg = f"{what} removed from {len(remove)} student{'s' if len(remove) != 1 else ''}."
        if kept:
            msg += f" {kept} already paid {'was' if kept == 1 else 'were'} kept."
        messages.success(request, msg)
        return redirect(back)
    return render(request, "office/charge_batch_delete.html", {
        "items": items, "first": first, "what": what, "settled": settled,
        "unsettled_count": len(items) - len(settled), "total": sum((c.amount for c in items), Decimal(0)),
    })
