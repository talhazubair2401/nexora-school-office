"""
Promotion to the next class at the start of the school year (April).

Every studying student moves up one class (by the class order: Play Group → Nursery → … → Class 10).
Students of the last class are marked "Passed out". Untick a student to keep them in the same class.
Every move is written to ClassHistory, so the student's old class stays on record and the whole
promotion can be undone.
"""
from datetime import date

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import ActivityLog, ClassHistory, ClassRoom, PromotionBatch, Student


def _plan():
    classes = list(ClassRoom.objects.order_by("order", "name"))
    plan = []
    for i, c in enumerate(classes):
        nxt = classes[i + 1] if i + 1 < len(classes) else None
        students = list(c.students.filter(status=Student.Status.ACTIVE).order_by("roll_no", "name"))
        plan.append({"c": c, "next": nxt, "students": students})
    return plan


def promote(request):
    today = timezone.localdate()
    # The new school year starts in April: Jan–May means this year's April, June onwards next year's.
    default_year = today.year if today.month <= 5 else today.year + 1
    try:
        year = int(request.POST.get("year") or request.GET.get("year") or default_year)
    except ValueError:
        year = default_year
    plan = _plan()
    done = PromotionBatch.objects.filter(session_year=year, undone_at__isnull=True).first()
    last = PromotionBatch.objects.filter(undone_at__isnull=True).first()

    if request.method == "POST":
        if done and not request.POST.get("again"):
            messages.error(request, f"Classes were already promoted for {year}–{year + 1}. Undo that first, "
                                    "or tick the box to promote again.")
            return redirect(f"{request.path}?year={year}")
        seen = set(int(x) for x in request.POST.getlist("seen") if x.isdigit())
        move = set(int(x) for x in request.POST.getlist("move") if x.isdigit())
        keep = seen - move      # unticked students stay in their class
        use_new_fee = request.POST.get("new_fee") == "1"
        renumber = request.POST.get("renumber") == "1"
        on = date(year, 4, 1)
        counts = {"PROMOTED": 0, "KEPT": 0, "PASSED": 0}
        with transaction.atomic():
            batch = PromotionBatch.objects.create(session_year=year, done_on=today, used_new_fee=use_new_fee)
            moves = []   # decide everything first from the current classes, then apply
            for row in plan:
                for s in row["students"]:
                    if s.pk in keep:
                        moves.append((s, row["c"], row["c"], ClassHistory.Result.KEPT))
                    elif row["next"] is None:
                        moves.append((s, row["c"], None, ClassHistory.Result.PASSED))
                    else:
                        moves.append((s, row["c"], row["next"], ClassHistory.Result.PROMOTED))
            for s, frm, to, result in moves:
                h = ClassHistory(batch=batch, student=s, from_class=frm, from_class_name=frm.name,
                                 to_class=to, to_class_name=to.name if to else "", result=result,
                                 old_roll=s.roll_no, old_fee=s.monthly_fee, new_fee=s.monthly_fee,
                                 old_status=s.status)
                if result == ClassHistory.Result.PROMOTED:
                    s.classroom = to
                    if use_new_fee and to.default_fee > 0:
                        s.monthly_fee = to.default_fee
                        if s.discount > s.monthly_fee:
                            s.discount = s.monthly_fee
                elif result == ClassHistory.Result.PASSED:
                    s.status = Student.Status.PASSED
                    s.left_on = on
                h.new_fee = s.monthly_fee
                s.save()
                h.save()
                counts[result] += 1
            if renumber:
                for c in ClassRoom.objects.all():
                    for n, st in enumerate(c.students.filter(status=Student.Status.ACTIVE).order_by("name"), start=1):
                        if st.roll_no != n:
                            st.roll_no = n
                            st.save(update_fields=["roll_no"])
        ActivityLog.add("promotion", f"Promoted classes for {year}–{year + 1}: {counts['PROMOTED']} moved up, "
                                     f"{counts['KEPT']} kept in the same class, {counts['PASSED']} passed out",
                        link=f"/classes/promote/?year={year}")
        messages.success(request, f"Done. {counts['PROMOTED']} students moved up, {counts['KEPT']} kept in their class, "
                                  f"{counts['PASSED']} marked as passed out. Their old classes are kept in each "
                                  "student's Class history. Fees already created for earlier months are not changed.")
        return redirect(f"{request.path}?year={year}")

    total = sum(len(r["students"]) for r in plan)
    return render(request, "office/promote.html", {
        "plan": plan, "year": year, "done": done, "last": last, "total": total,
        "years": [default_year - 1, default_year, default_year + 1],
        "batches": PromotionBatch.objects.all()[:10],
    })


@require_POST
def promote_undo(request, pk):
    batch = get_object_or_404(PromotionBatch, pk=pk, undone_at__isnull=True)
    newest = PromotionBatch.objects.filter(undone_at__isnull=True).first()
    if newest and newest.pk != batch.pk:
        messages.error(request, "Only the most recent promotion can be undone.")
        return redirect("office:promote")
    n = 0
    with transaction.atomic():
        for h in batch.entries.select_related("student"):
            s = h.student
            s.classroom = h.from_class
            s.roll_no = h.old_roll
            if s.monthly_fee == h.new_fee:      # leave it if someone changed the fee by hand since
                s.monthly_fee = h.old_fee
            if h.result == ClassHistory.Result.PASSED and s.status == Student.Status.PASSED:
                s.status = h.old_status or Student.Status.ACTIVE
                s.left_on = None
            s.save()
            n += 1
        batch.undone_at = timezone.now()
        batch.save(update_fields=["undone_at"])
    ActivityLog.add("promotion", f"Undid the promotion for {batch.session_year}–{batch.session_year + 1} "
                                 f"({n} students back in their old classes)", link="/classes/promote/")
    messages.success(request, f"Promotion undone: {n} students are back in their previous classes.")
    return redirect(f"/classes/promote/?year={batch.session_year}")
