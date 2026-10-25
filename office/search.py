"""
Student search used by the Students page and the search bar at the top.

Rules
  * Letters: the student's own name is matched from the start of a word
    ("ali" finds "Ali Raza" and "Muhammad Ali", not "Khalid"). Every word typed
    must match. Students whose FATHER's name matches are listed separately below.
  * Numbers only: just the admission number and the phone number are searched.
  * "Search in" can limit the search to one field.
"""
import re
from django.conf import settings

FIELDS = [("all", "Everything"), ("name", "Student name"), ("father", "Father's name"),
          ("adm", "Admission no."), ("phone", "Phone")]

SORTS = {
    "name": lambda s: (s.name.lower(), s.father_name.lower()),
    "father": lambda s: ((s.father_name or "~").lower(), s.name.lower()),
    "adm": lambda s: s.admission_no,
    "class": lambda s: (s.classroom.order if s.classroom else 999, s.roll_no or 0, s.name.lower()),
    "roll": lambda s: (s.roll_no if s.roll_no is not None else 10**6, s.name.lower()),
    "fee": lambda s: (s.net_fee, s.name.lower()),
    "phone": lambda s: (s.phone or "~", s.name.lower()),
    "status": lambda s: (s.status, s.name.lower()),
}


def digits(text):
    return re.sub(r"\D", "", text or "")


def is_number_query(q):
    """'0301-668', '0012', '2026 12' -> True."""
    return bool(q) and bool(re.fullmatch(r"[\d\s\-+]+", q)) and bool(digits(q))


def words_match(text, q):
    """Every word in q starts a word in text (case-insensitive)."""
    text_words = re.split(r"[\s.\-]+", (text or "").lower())
    for w in q.lower().split():
        if not any(t.startswith(w) for t in text_words if t):
            return False
    return True


def contains(text, q):
    return q.lower() in (text or "").lower()


def adm_match(s, q):
    d = digits(q)
    serial = s.admission_no.rsplit("-", 1)[-1]
    if q.upper() in s.admission_no.upper():
        return True
    if d and (serial.lstrip("0") == d.lstrip("0") or serial.startswith(d)):
        return True
    return bool(d) and len(d) >= 5 and d in digits(s.admission_no)


def phone_match(s, q):
    d = digits(q)
    return len(d) >= 3 and d in digits(s.phone)


def search(students, q, field="all"):
    """
    Returns a list of (group_key, group_title, [students]) - groups that are empty are left out.
    `students` is any iterable of Student objects (already filtered by class/status).
    """
    q = (q or "").strip()
    students = list(students)
    if not q:
        return [("all", "", students)]
    if field not in dict(FIELDS):
        field = "all"
    groups = {"exact": [], "name": [], "father": [], "adm": [], "phone": [], "other": []}
    numeric = is_number_query(q)
    for s in students:
        if field in ("all", "adm") and (numeric or field == "adm" or q.upper().startswith(settings.ADMISSION_PREFIX)) and adm_match(s, q):
            serial = s.admission_no.rsplit("-", 1)[-1]
            exact = digits(q) and (serial.lstrip("0") == digits(q).lstrip("0") or s.admission_no.upper() == q.upper())
            groups["exact" if exact else "adm"].append(s)
        elif field in ("all", "phone") and (numeric or field == "phone") and phone_match(s, q):
            groups["phone"].append(s)
        elif numeric and field == "all":
            continue
        elif field in ("all", "name") and words_match(s.name, q):
            groups["name"].append(s)
        elif field in ("all", "father") and words_match(s.father_name, q):
            groups["father"].append(s)
        elif field == "all" and len(q) >= 3 and (contains(s.name, q) or contains(s.b_form_no, q)):
            groups["other"].append(s)   # e.g. "li" inside "Khalid" - shown last
    titles = {"exact": f"Admission no. {q}", "name": "Student name matches", "father": "Father's name matches",
              "adm": "Admission number matches", "phone": "Phone number matches",
              "other": "Other matches (inside a name or B-Form no.)"}
    order = ["exact", "adm", "phone", "name", "father", "other"]
    return [(k, titles[k], groups[k]) for k in order if groups[k]]


def sort_students(students, sort):
    """sort is e.g. 'name' or '-fee'."""
    key = (sort or "name").lstrip("-")
    fn = SORTS.get(key, SORTS["name"])
    return sorted(students, key=fn, reverse=(sort or "").startswith("-"))
