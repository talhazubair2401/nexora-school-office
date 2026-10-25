"""
Certificates and letters: what each one asks for, filled in from the records.

Each kind has a list of fields (key, label, kind, help). The office can change any value before
issuing; the values are saved with the certificate so a reprint looks exactly the same.
"""
from datetime import date

from django.utils import timezone

from .models import Certificate, ClassHistory, ClassRoom, Fee, Student

CONDUCT = ["Excellent", "Very good", "Good", "Satisfactory"]

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
        "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
ORD = {1: "First", 2: "Second", 3: "Third", 4: "Fourth", 5: "Fifth", 6: "Sixth", 7: "Seventh", 8: "Eighth",
       9: "Ninth", 10: "Tenth", 11: "Eleventh", 12: "Twelfth", 13: "Thirteenth", 14: "Fourteenth", 15: "Fifteenth",
       16: "Sixteenth", 17: "Seventeenth", 18: "Eighteenth", 19: "Nineteenth", 20: "Twentieth", 30: "Thirtieth"}


def _num_words(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " Hundred" + (" and " + _num_words(n % 100) if n % 100 else "")
    return _num_words(n // 1000) + " Thousand" + (" " + _num_words(n % 1000) if n % 1000 else "")


def _day_words(d):
    if d in ORD:
        return ORD[d]
    tens = TENS[d // 10]
    return f"{tens}-{ORD[d % 10].lower()}"


def date_in_words(d):
    """date(2018, 3, 15) -> 'Fifteenth March, Two Thousand Eighteen'."""
    if not d:
        return ""
    return f"{_day_words(d.day)} {d:%B}, {_num_words(d.year)}"


def parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# key, label, input type, help text
F = {
    "name": ("Name", "text", ""),
    "father_name": ("Father's name", "text", ""),
    "gender": ("Boy / girl (for he / she)", "gender", ""),
    "admission_no": ("Admission no.", "text", ""),
    "admission_date": ("Date of admission", "date", ""),
    "class_admitted": ("Class at admission", "text", ""),
    "class_now": ("Class", "text", ""),
    "class_leaving": ("Class at leaving", "text", ""),
    "dob": ("Date of birth", "date", "Written in words automatically"),
    "b_form_no": ("B-Form no.", "text", ""),
    "leaving_date": ("Date of leaving", "date", ""),
    "reason": ("Reason for leaving", "text", ""),
    "conduct": ("Conduct and character", "conduct", ""),
    "promotion": ("Fit for promotion to", "text", "e.g. Class 6, or leave empty"),
    "fee_status": ("Fee / dues", "text", ""),
    "from_date": ("Studied here from", "date", ""),
    "to_date": ("Studied here up to", "date", "Leave empty for “till date”"),
    "exam": ("Examination", "text", ""),
    "board": ("Board", "text", ""),
    "exam_year": ("Year of examination", "text", ""),
    "board_roll": ("Board roll no.", "text", ""),
    "marks": ("Marks obtained", "text", ""),
    "total_marks": ("Total marks", "text", ""),
    "grade": ("Grade / division", "text", ""),
    "session": ("Session", "text", "e.g. 2024–2026"),
    "cnic": ("CNIC", "text", ""),
    "designation": ("Designation", "text", ""),
    "subjects": ("Subjects / classes taught", "text", ""),
    "join_date": ("Joining date", "date", ""),
    "end_date": ("Last working day", "date", "Leave empty for “till date” (still working)"),
    "relieve_reason": ("Reason", "text", "e.g. on her own request (resignation)"),
    "appreciation": ("Appreciated for", "textarea", ""),
    "remarks": ("Remarks (optional)", "textarea", "An extra line printed under the main text"),
    "issued_on": ("Date of issue", "date", ""),
}

FIELDS = {
    "SLC": ["name", "father_name", "gender", "admission_no", "b_form_no", "dob", "admission_date", "class_admitted",
            "class_leaving", "leaving_date", "reason", "conduct", "promotion", "fee_status", "remarks", "issued_on"],
    "CHAR": ["name", "father_name", "gender", "admission_no", "class_now", "from_date", "to_date", "conduct",
             "remarks", "issued_on"],
    "DOB": ["name", "father_name", "gender", "admission_no", "b_form_no", "dob", "admission_date", "class_now",
            "remarks", "issued_on"],
    "PASS": ["name", "father_name", "gender", "admission_no", "session", "exam", "board", "exam_year", "board_roll",
             "marks", "total_marks", "grade", "conduct", "remarks", "issued_on"],
    "EXP": ["name", "father_name", "gender", "cnic", "designation", "subjects", "join_date", "end_date", "conduct",
            "remarks", "issued_on"],
    "REL": ["name", "father_name", "gender", "cnic", "designation", "join_date", "end_date", "relieve_reason",
            "conduct", "remarks", "issued_on"],
    "APP": ["name", "father_name", "gender", "designation", "appreciation", "remarks", "issued_on"],
}
DATE_KEYS = {k for k, v in F.items() if v[1] == "date"}


def _fee_status(s):
    due = s.balance_due()
    if due > 0:
        return f"Rs. {due:,.0f} still due"
    last = (Fee.objects.filter(student=s).order_by("-month").prefetch_related("payments").first())
    if last:
        return f"All dues cleared (paid up to {last.month:%B %Y})"
    return "All dues cleared"


def _next_class(classroom):
    if not classroom:
        return ""
    nxt = ClassRoom.objects.filter(order__gt=classroom.order).order_by("order").first()
    return nxt.name if nxt else ""


def initial_for_student(kind, s):
    today = timezone.localdate()
    first = ClassHistory.objects.filter(student=s).order_by("batch__session_year", "id").first()
    class_admitted = first.from_class_name if first else str(s.classroom or "")
    d = {
        "name": s.name, "father_name": s.father_name, "gender": s.gender, "admission_no": s.admission_no,
        "admission_date": s.admission_date, "class_admitted": class_admitted, "class_now": str(s.classroom or ""),
        "class_leaving": str(s.classroom or ""), "dob": s.date_of_birth, "b_form_no": s.b_form_no,
        "leaving_date": s.left_on or today, "reason": "Parents' wish", "conduct": "Good",
        "promotion": "", "fee_status": "", "from_date": s.admission_date, "to_date": s.left_on,
        "issued_on": today, "remarks": "",
        "exam": "Secondary School Certificate (Matric) Examination",
        "board": "Board of Intermediate and Secondary Education, Lahore",
        "exam_year": str(today.year), "board_roll": "", "marks": "", "total_marks": "", "grade": "",
        "session": "",
    }
    if kind == "SLC":
        d["fee_status"] = _fee_status(s)
        if s.status == Student.Status.PASSED:
            d["reason"] = "Passed out (completed Class 10)"
    if kind == "PASS":
        start = s.admission_date.year if s.admission_date else today.year - 2
        d["session"] = f"{max(start, (s.left_on or today).year - 2)}–{(s.left_on or today).year}"
    return d


def initial_for_teacher(kind, t):
    today = timezone.localdate()
    return {
        "name": t.name, "father_name": t.father_name, "gender": t.gender, "cnic": t.cnic,
        "designation": "Teacher", "subjects": t.subjects, "join_date": t.joining_date,
        "end_date": t.left_on if (t.left_on or kind == "EXP") else today,
        "relieve_reason": "on own request (resignation accepted)", "conduct": "Very good",
        "appreciation": "excellent teaching, hard work and dedication, and for the good results of the students "
                        f"in the annual examinations {today.year}",
        "remarks": "", "issued_on": today,
    }


def clean_data(kind, source):
    """Take the posted / GET values for this kind; dates are kept as YYYY-MM-DD text."""
    out = {}
    for key in FIELDS[kind]:
        v = source.get(key, "")
        if isinstance(v, date):
            v = v.isoformat()
        out[key] = (v or "").strip() if isinstance(v, str) else v
        if key in DATE_KEYS and out[key] and not parse_date(out[key]):
            out[key] = ""
    return out


def to_form_values(data):
    return {k: (v.isoformat() if isinstance(v, date) else (v or "")) for k, v in data.items()}


def pronouns(gender):
    if gender == "F":
        return {"he": "she", "He": "She", "his": "her", "His": "Her", "him": "her", "son": "daughter",
                "so": "D/o", "mr": "Ms.", "child": "daughter"}
    if gender == "M":
        return {"he": "he", "He": "He", "his": "his", "His": "His", "him": "him", "son": "son",
                "so": "S/o", "mr": "Mr.", "child": "son"}
    return {"he": "he/she", "He": "He/She", "his": "his/her", "His": "His/Her", "him": "him/her",
            "son": "son/daughter", "so": "S/o / D/o", "mr": "Mr./Ms.", "child": "son/daughter"}


PRINT_TITLES = {"PASS": "Matric Passing Certificate", "DOB": "Date of Birth Certificate"}


def render_context(kind, data, serial="", preview=False):
    """Everything the certificate template needs."""
    d = dict(data)
    for k in DATE_KEYS:
        if k in d:
            d[k] = parse_date(d[k])
    body = data.get("body_html") or ""
    return {
        "body_html": mark_safe(clean_html(body)) if body else "",
        "kind": kind, "title": PRINT_TITLES.get(kind, dict(Certificate.Kind.choices)[kind]), "d": d, "p": pronouns(d.get("gender", "")),
        "dob_words": date_in_words(d.get("dob")), "serial": serial, "preview": preview,
        "teacher_doc": kind in Certificate.TEACHER_KINDS,
    }


# ---------------------------------------------------------------------------
# Wording edited by hand on the certificate
# ---------------------------------------------------------------------------
import re  # noqa: E402
from html import escape  # noqa: E402
from html.parser import HTMLParser  # noqa: E402

from django.utils.safestring import mark_safe  # noqa: E402

ALLOWED_TAGS = {"p", "b", "strong", "i", "em", "u", "br", "div", "span", "table", "tbody", "tr", "td", "h1", "font"}
VOID = {"br"}
SAFE_STYLE = re.compile(r"^\s*(min-width|text-align|font-weight|font-style|text-decoration)\s*:\s*[#\w\s.%-]+;?\s*$")


class _Clean(HTMLParser):
    """Keeps only simple formatting (bold, italic, underline, paragraphs, the details table)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object"):
            self.skip += 1
            return
        if tag not in ALLOWED_TAGS or self.skip:
            return
        keep = []
        for k, v in attrs:
            if k == "class" and v and re.fullmatch(r"[\w\s-]+", v):
                keep.append(f' class="{escape(v)}"')
            elif k == "style" and v and all(SAFE_STYLE.match(part + ";") for part in v.split(";") if part.strip()):
                keep.append(f' style="{escape(v)}"')
        self.out.append(f"<{tag}{''.join(keep)}>")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object"):
            self.skip = max(self.skip - 1, 0)
            return
        if tag in self.stack and not self.skip:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data))


def clean_html(html):
    if not html:
        return ""
    p = _Clean()
    p.feed(str(html)[:60000])
    p.close()
    while p.stack:
        p.out.append(f"</{p.stack.pop()}>")
    return "".join(p.out).strip()


def body_from(source):
    """The hand-edited wording posted with the form, or '' when the standard wording is used."""
    if source.get("body_custom") != "1":
        return ""
    return clean_html(source.get("body_html", ""))
