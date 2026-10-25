from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..forms import TestForm
from ..models import ActivityLog, ClassRoom, Mark, School, Student, Test, TestRemark, TestSubject
from ..results import test_results, test_students


def test_list(request):
    tests = Test.objects.select_related("classroom").prefetch_related("subjects")
    cls = request.GET.get("class", "")
    kind = request.GET.get("kind", "")
    if cls.isdigit():
        tests = tests.filter(classroom_id=int(cls))
    if kind in Test.Kind.values:
        tests = tests.filter(kind=kind)
    return render(request, "office/test_list.html", {
        "tests": tests[:200], "classes": ClassRoom.objects.all(), "cls": cls, "kind": kind,
        "kinds": Test.Kind.choices,
    })


def _read_subjects(post):
    """Subject rows from the form: names[] / full[] / ids[]. Returns (rows, errors)."""
    names, fulls, ids = post.getlist("subj_name"), post.getlist("subj_full"), post.getlist("subj_id")
    rows, errors = [], []
    for i, name in enumerate(names):
        name = name.strip()
        if not name:
            continue
        try:
            full = Decimal(fulls[i])
            if full <= 0:
                raise InvalidOperation
        except (InvalidOperation, IndexError):
            errors.append(f"Full marks for {name} must be a number above 0.")
            continue
        rows.append({"id": ids[i] if i < len(ids) else "", "name": name[:60], "full": full})
    if not rows and not errors:
        errors.append("Add at least one subject.")
    return rows, errors


def test_create(request):
    initial = {}
    cls = request.GET.get("class", "")
    if cls.isdigit():
        initial["classroom"] = int(cls)
    form = TestForm(request.POST or None, initial=initial)
    subject_rows, errors = [], []
    if request.method == "POST":
        subject_rows, errors = _read_subjects(request.POST)
        if form.is_valid() and not errors:
            with transaction.atomic():
                test = form.save()
                for i, r in enumerate(subject_rows, start=1):
                    TestSubject.objects.create(test=test, name=r["name"], full_marks=r["full"], order=i)
            ActivityLog.add("test", f"New test: {test.name} for {test.classroom}", link=test)
            messages.success(request, f"{test.name} created for {test.classroom}. Now enter the marks.")
            return redirect("office:marks_entry", pk=test.pk)
    class_subjects = {c.pk: [s.name for s in c.subjects.all()] for c in ClassRoom.objects.prefetch_related("subjects")}
    return render(request, "office/test_form.html", {
        "form": form, "title": "New test", "subject_rows": subject_rows, "errors": errors,
        "class_subjects": class_subjects,
    })


def test_edit(request, pk):
    test = get_object_or_404(Test, pk=pk)
    form = TestForm(request.POST or None, instance=test)
    form.fields["classroom"].disabled = True
    subject_rows = [{"id": s.pk, "name": s.name, "full": s.full_marks} for s in test.subjects.all()]
    errors = []
    if request.method == "POST":
        subject_rows, errors = _read_subjects(request.POST)
        if form.is_valid() and not errors:
            with transaction.atomic():
                form.save()
                keep = []
                for i, r in enumerate(subject_rows, start=1):
                    ts = test.subjects.filter(pk=r["id"]).first() if str(r["id"]).isdigit() else None
                    if ts:
                        ts.name, ts.full_marks, ts.order = r["name"], r["full"], i
                        ts.save()
                    else:
                        ts = TestSubject.objects.create(test=test, name=r["name"], full_marks=r["full"], order=i)
                    keep.append(ts.pk)
                removed = test.subjects.exclude(pk__in=keep)
                n_removed = removed.count()
                removed.delete()
            ActivityLog.add("test", f"Test edited: {test.name} ({test.classroom})", link=test)
            messages.success(request, "Test saved." + (f" {n_removed} subject(s) and their marks removed." if n_removed else ""))
            return redirect(test)
    return render(request, "office/test_form.html", {
        "form": form, "title": f"Edit {test.name}", "test": test, "subject_rows": subject_rows,
        "errors": errors, "class_subjects": {},
    })


def test_delete(request, pk):
    test = get_object_or_404(Test, pk=pk)
    if request.method == "POST":
        test.delete()
        ActivityLog.add("test", f"Test deleted: {test.name} ({test.classroom})")
        messages.success(request, f"{test.name} deleted with all its marks.")
        return redirect("office:test_list")
    return render(request, "office/confirm.html", {
        "title": f"Delete {test.name}?", "message": f"All marks entered for {test.classroom} in this test are deleted.",
        "button": "Delete test", "cancel_url": test.get_absolute_url(),
    })


def test_detail(request, pk):
    test = get_object_or_404(Test.objects.select_related("classroom"), pk=pk)
    subjects, rows = test_results(test)
    ranked = sorted([r for r in rows if r["position"]], key=lambda r: r["position"])
    done = [r for r in rows if r["percent"] is not None]
    return render(request, "office/test_detail.html", {
        "test": test, "subjects": subjects, "rows": rows, "top": ranked[:3],
        "entered": len(done), "average": round(sum(r["percent"] for r in done) / len(done), 1) if done else None,
        "passed": sum(1 for r in done if r["passed"]),
    })


def marks_entry(request, pk):
    test = get_object_or_404(Test.objects.select_related("classroom"), pk=pk)
    subjects = list(test.subjects.all())
    students = test_students(test)
    existing = {(m.student_id, m.subject_id): m for m in Mark.objects.filter(subject__test=test)}
    remarks = {r.student_id: r for r in TestRemark.objects.filter(test=test)}
    errors = {}

    if request.method == "POST":
        to_save = []
        for st in students:
            for sub in subjects:
                key = f"m_{st.pk}_{sub.pk}"
                raw = (request.POST.get(key) or "").strip()
                absent = request.POST.get(f"a_{st.pk}_{sub.pk}") == "on" or raw.upper() in ("A", "ABS")
                value = None
                if raw and not absent:
                    try:
                        value = Decimal(raw)
                        if value < 0 or value > sub.full_marks:
                            raise InvalidOperation
                    except InvalidOperation:
                        errors[key] = f"0–{sub.full_marks:g}"
                        continue
                to_save.append((st, sub, value, absent))
        if errors:
            messages.error(request, "Some marks are wrong (shown in red). Marks can't be more than the full marks. Nothing was saved.")
        else:
            with transaction.atomic():
                for st, sub, value, absent in to_save:
                    m = existing.get((st.pk, sub.pk))
                    if value is None and not absent:
                        if m:
                            m.delete()
                        continue
                    if m:
                        m.obtained, m.absent = value, absent
                        m.save()
                    else:
                        Mark.objects.create(subject=sub, student=st, obtained=value, absent=absent)
                for st in students:
                    text = (request.POST.get(f"r_{st.pk}") or "").strip()[:250]
                    r = remarks.get(st.pk)
                    if r:
                        r.text = text
                        r.save()
                    elif text:
                        TestRemark.objects.create(test=test, student=st, text=text)
            ActivityLog.add("test", f"Marks saved: {test.name} ({test.classroom})", link=test)
            messages.success(request, "Marks saved.")
            if "finish" in request.POST:
                return redirect(test)
            return redirect("office:marks_entry", pk=test.pk)

    grid = []
    for st in students:
        cells = []
        for sub in subjects:
            key = f"m_{st.pk}_{sub.pk}"
            m = existing.get((st.pk, sub.pk))
            if request.method == "POST":
                val = request.POST.get(key, "")
                absent = request.POST.get(f"a_{st.pk}_{sub.pk}") == "on"
            else:
                val = "" if not m or m.obtained is None else f"{float(m.obtained):g}"
                absent = bool(m and m.absent)
            cells.append({"key": key, "akey": f"a_{st.pk}_{sub.pk}", "value": val, "absent": absent,
                          "error": errors.get(key), "full": sub.full_marks, "name": sub.name})
        remark = request.POST.get(f"r_{st.pk}", "") if request.method == "POST" else (
            remarks[st.pk].text if st.pk in remarks else "")
        grid.append({"student": st, "cells": cells, "remark": remark})
    return render(request, "office/marks_entry.html", {"test": test, "subjects": subjects, "grid": grid})


def result_sheet(request, pk):
    test = get_object_or_404(Test.objects.select_related("classroom"), pk=pk)
    subjects, rows = test_results(test)
    order = request.GET.get("order", "position")
    if order == "position":
        rows = sorted(rows, key=lambda r: (r["position"] is None, r["position"] or 0, r["student"].roll_no or 0))
    return render(request, "print/result_sheet.html", {"test": test, "subjects": subjects, "rows": rows})


def result_cards(request, pk):
    """Result card for one student (?student=ID) or for the whole class."""
    test = get_object_or_404(Test.objects.select_related("classroom"), pk=pk)
    subjects, rows = test_results(test)
    sid = request.GET.get("student", "")
    if sid.isdigit():
        rows = [r for r in rows if r["student"].pk == int(sid)]
    rows = [r for r in rows if r["percent"] is not None]
    if not rows:
        messages.info(request, "No marks entered yet, so there's no result card to print.")
        return redirect(test)
    class_size = sum(1 for r in test_results(test)[1] if r["percent"] is not None)
    return render(request, "print/result_card.html", {"test": test, "subjects": subjects, "rows": rows,
                                                       "class_size": class_size})
