"""Totals, percentages, grades and positions for a test."""
from decimal import Decimal

from .models import Mark, School, Student, TestRemark


def test_students(test):
    """Students in the test: everyone now studying in the class, plus anyone who already has marks."""
    with_marks = Student.objects.filter(marks__subject__test=test)
    qs = Student.objects.filter(classroom=test.classroom, status=Student.Status.ACTIVE) | with_marks
    return list(qs.distinct().order_by("roll_no", "name"))


def test_results(test, school=None):
    """
    Returns (subjects, rows). Each row:
      student, marks {subject_id: Mark}, obtained, total, percent, grade, passed, position, remark, complete
    Rows are in roll-number order; `position` is 1, 2, 2, 4 … by percentage.
    """
    school = school or School.get()
    subjects = list(test.subjects.all())
    students = test_students(test)
    marks = {}
    for m in Mark.objects.filter(subject__test=test):
        marks.setdefault(m.student_id, {})[m.subject_id] = m
    remarks = dict(TestRemark.objects.filter(test=test).values_list("student_id", "text"))
    full_total = sum((s.full_marks for s in subjects), Decimal(0))

    rows = []
    for st in students:
        sm = marks.get(st.pk, {})
        entered = [m for m in sm.values() if m.absent or m.obtained is not None]
        obtained = sum((m.obtained or 0 for m in sm.values() if not m.absent), Decimal(0))
        percent = round(float(obtained) * 100 / float(full_total), 1) if entered and full_total else None
        rows.append({
            "student": st, "marks": sm, "obtained": obtained, "total": full_total, "percent": percent,
            "grade": school.grade_for(percent) if percent is not None else "-",
            "passed": percent is not None and percent >= school.pass_percent,
            "remark": remarks.get(st.pk, ""),
            "complete": len(entered) == len(subjects) and bool(subjects),
            "position": None,
        })

    ranked = sorted([r for r in rows if r["percent"] is not None], key=lambda r: -r["percent"])
    last, pos = None, 0
    for i, r in enumerate(ranked, start=1):
        if r["percent"] != last:
            pos, last = i, r["percent"]
        r["position"] = pos
    return subjects, rows


def ordinal(n):
    if n is None:
        return "-"
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
