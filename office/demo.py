"""
Public online demo (portfolio) — only active when SCHOOL_DEMO=1.

Builds a complete FICTIONAL school ("Nexora Model School"): classes, teachers, students,
fees and receipts, salaries, tests and marks, attendance, paper fund, expenses and
certificates. Every name, phone number and CNIC is generated; nothing comes from a real
school. The data is rebuilt on first use and again once it is older than DEMO_RESET_HOURS.

Visitors sign in with one click (owner, or one of two office staff logins). Demo logins
have no usable password. Password changes, logins, backups and settings are switched off.
Nothing here runs unless DEMO_MODE is on, so it can never touch a school's real records.
"""
import datetime as dt
import random
import shutil
import threading
import time
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.core.management import call_command
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone

DEMO_ACCOUNTS = [
    # username, role label, description, staff permissions (None = owner)
    ("admin", "Principal (owner)", "Everything: fees, salaries, profit, settings, logins and the activity log.", None),
    ("demo_clerk", "Office clerk · Ayesha", "Receives fees, prints receipts and challans, marks attendance, admits students.",
     {"fees": True, "attendance": True, "students": True, "tests": False, "certificates": False}),
    ("demo_exams", "Exams teacher · Mr. Hamid", "Makes tests, types marks, prints result cards and certificates.",
     {"fees": False, "attendance": True, "students": False, "tests": True, "certificates": True}),
]
DEMO_USERNAMES = {a[0] for a in DEMO_ACCOUNTS}
STAFF_NAMES = {"demo_clerk": "Ayesha (Office clerk)", "demo_exams": "Mr. Hamid (Exams)"}

# Pages switched off in the public demo, with the reason shown to the visitor.
BLOCKED = {
    "change_password": "Password changes are switched off in the public demo.",
    "backup": "Backups are switched off in the public demo. In the office edition this saves a dated copy to a USB stick.",
    "closing": None,  # the backup reminder at log-out is skipped
    "user_create": "Adding logins is switched off in the public demo.",
    "user_edit": "Changing logins is switched off in the public demo.",
    "user_delete": "Removing logins is switched off in the public demo.",
}
BLOCKED_POST = {"settings": "Settings can be viewed but not saved in the public demo, so every visitor sees the same school."}

_lock = threading.Lock()
_last_check = 0.0


# ---------------------------------------------------------------------------
# Reset schedule
# ---------------------------------------------------------------------------
def _marker():
    return settings.DATA_DIR / "demo_built_at.txt"


def built_at():
    try:
        return dt.datetime.fromisoformat(_marker().read_text().strip())
    except (OSError, ValueError):
        return None


def next_reset():
    b = built_at()
    return b + dt.timedelta(hours=settings.DEMO_RESET_HOURS) if b else None


def is_stale():
    b = built_at()
    return b is None or dt.datetime.now() - b >= dt.timedelta(hours=settings.DEMO_RESET_HOURS)


def ensure_fresh():
    global _last_check
    if time.monotonic() - _last_check < 30:
        return
    with _lock:
        if time.monotonic() - _last_check < 30:
            return
        try:
            if is_stale():
                build_demo()
        finally:
            _last_check = time.monotonic()


# ---------------------------------------------------------------------------
# Middleware and the one-click sign-in
# ---------------------------------------------------------------------------
class DemoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEMO_MODE and not request.path.startswith(("/static/", "/media/")):
            ensure_fresh()
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not settings.DEMO_MODE:
            return None
        match = request.resolver_match
        name = match.url_name if match else None
        if name == "closing":  # skip the "back up before you lock" screen
            logout(request)
            return redirect("office:login")
        msg = BLOCKED.get(name) or (BLOCKED_POST.get(name) if request.method == "POST" else None)
        if msg:
            messages.info(request, msg)
            back = request.META.get("HTTP_REFERER") or ""
            return redirect(back if back.startswith(("/", request.build_absolute_uri("/"))) else "office:dashboard")
        return None


def demo_login(request):
    if not settings.DEMO_MODE or request.method != "POST":
        return redirect("office:login")
    username = request.POST.get("username") or ""
    if username not in DEMO_USERNAMES:
        return redirect("office:login")
    user = get_user_model().objects.filter(username=username, is_active=True).first()
    if not user:
        return redirect("office:login")
    if request.user.is_authenticated:
        logout(request)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    from .access import display_name, set_current_user
    from .models import ActivityLog
    set_current_user(user)
    ActivityLog.add("login", f"{display_name(user)} logged in (demo)")
    return redirect("office:dashboard")


# ---------------------------------------------------------------------------
# Fictional data
# ---------------------------------------------------------------------------
BOYS = ["Ahmed", "Ali", "Hamza", "Usman", "Bilal", "Hassan", "Hussain", "Umar", "Zain", "Saad", "Abdullah", "Ibrahim",
        "Musa", "Rayyan", "Arham", "Ayaan", "Haris", "Talha", "Fahad", "Danish", "Shayan", "Faizan", "Huzaifa", "Owais",
        "Rehan", "Taimoor", "Yasir", "Junaid", "Moiz", "Anas", "Zohaib", "Daniyal", "Shahzaib", "Hadi", "Affan"]
GIRLS = ["Ayesha", "Fatima", "Zainab", "Maryam", "Hira", "Sana", "Iqra", "Areeba", "Aiman", "Hafsa", "Khadija",
         "Mahnoor", "Laiba", "Eman", "Anaya", "Hoorain", "Alishba", "Rimsha", "Noor", "Aleena", "Minahil", "Zoya",
         "Amna", "Rabia", "Javeria", "Sidra", "Mehwish", "Komal", "Dua", "Inaya"]
FATHERS = ["Muhammad Aslam", "Tariq Mehmood", "Khalid Hussain", "Shahid Iqbal", "Imran Ali", "Naveed Akhtar",
           "Zafar Iqbal", "Asif Javed", "Rizwan Ahmed", "Kashif Butt", "Waqas Ahmad", "Sajid Mahmood", "Nadeem Abbas",
           "Arshad Ali", "Amjad Hussain", "Faisal Rafiq", "Abdul Rehman", "Shoaib Akram", "Ghulam Murtaza",
           "Mushtaq Ahmed", "Javed Iqbal", "Rashid Mehmood", "Adnan Saleem", "Babar Ali", "Liaqat Ali", "Pervaiz Akhtar",
           "Sohail Anwar", "Qaiser Abbas", "Usman Ghani", "Hafiz Naeem"]
MOTHERS = ["Nasreen", "Shazia", "Rubina", "Saima", "Samina", "Farzana", "Nighat", "Asma", "Bushra", "Uzma", "Shabnam",
           "Kiran", "Rukhsana", "Tahira", "Nadia"]
AREAS = ["Model Town", "Johar Town", "Township", "Green Town", "Faisal Town", "Garden Town", "Iqbal Town", "Wapda Town"]
CLASSES = [("Play Group", 3000, 4), ("Nursery", 3000, 5), ("Prep", 3200, 6), ("Class 1", 3500, 7),
           ("Class 2", 3500, 8), ("Class 3", 3800, 9), ("Class 4", 3800, 10), ("Class 5", 4000, 11),
           ("Class 6", 4500, 12), ("Class 7", 4500, 13), ("Class 8", 4800, 14), ("Class 9", 5500, 15),
           ("Class 10", 5500, 16)]
SUBJECTS = {
    "early": ["English", "Urdu", "Maths", "General Knowledge"],
    "primary": ["English", "Urdu", "Maths", "Science", "Islamiat", "Social Studies"],
    "middle": ["English", "Urdu", "Maths", "Science", "Islamiat", "Social Studies", "Computer"],
    "senior": ["English", "Urdu", "Maths", "Physics", "Chemistry", "Biology", "Islamiat", "Pakistan Studies"],
}
TEACHERS = [
    ("Mrs. Saima Tariq", "F", "M.A. English, B.Ed", "English", 32000), ("Mr. Hamid Raza", "M", "M.Sc. Physics", "Physics, Maths", 35000),
    ("Ms. Hina Kanwal", "F", "M.Sc. Chemistry", "Chemistry, Science", 30000), ("Mr. Adeel Anwar", "M", "M.Sc. Mathematics", "Maths", 32000),
    ("Ms. Sadia Noreen", "F", "M.A. Urdu", "Urdu", 25000), ("Mr. Qari Abdul Basit", "M", "M.A. Islamiat", "Islamiat, Nazra", 22000),
    ("Ms. Rabia Saleem", "F", "B.S. Botany", "Biology, Science", 28000), ("Ms. Nimra Javed", "F", "B.S. Computer Science", "Computer", 25000),
    ("Ms. Farah Naz", "F", "B.A., Montessori diploma", "Play Group, Nursery", 18000), ("Ms. Uzma Shaheen", "F", "B.A., PTC", "Prep, Class 1", 18000),
    ("Ms. Kiran Shahzadi", "F", "B.A., B.Ed", "Class 2, Class 3", 20000), ("Ms. Mehreen Akhtar", "F", "M.A. History", "Social Studies, Pakistan Studies", 24000),
    ("Mr. Naeem Akhtar", "M", "B.Com", "Class 4, Class 5", 20000), ("Mr. Waseem Abbas", "M", "F.A.", "Office & accounts", 20000),
]


def _phone(r):
    return f"0300-0{r.randint(100000, 999999)}"  # fictional numbers in one recognisable range


def _cnic(r):
    return f"35202-{r.randint(1000000, 9999999)}-{r.randint(1, 9)}"


def _school_days(start, end):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def build_demo():
    if not settings.DEMO_MODE:
        raise RuntimeError("build_demo() only runs when SCHOOL_DEMO=1.")
    call_command("migrate", interactive=False, verbosity=0)
    call_command("flush", interactive=False, verbosity=0)
    media = settings.MEDIA_ROOT
    if media.exists():
        shutil.rmtree(media, ignore_errors=True)
    media.mkdir(parents=True, exist_ok=True)
    with transaction.atomic():
        _populate()
    _marker().write_text(dt.datetime.now().isoformat(timespec="seconds"))


def _populate():
    from . import access
    from .models import (ActivityLog, Certificate, Charge, ClassRoom, CLASS_COLOURS, Expense, Fee, FeePayment, Mark,
                         Salary, School, StaffAccess, Student, StudentAttendance, Subject, Teacher, TeacherAttendance,
                         Test, TestRemark, TestSubject, add_months, month_start, session_start)
    from . import certificates as C

    r = random.Random(2026)
    today = timezone.localdate()
    User = get_user_model()

    # Logins (no usable passwords: sign-in is one click)
    owner = User(username="admin", is_staff=True, is_superuser=True)
    owner.set_unusable_password()
    owner.save()
    staff = {}
    for username, _label, _desc, perms in DEMO_ACCOUNTS[1:]:
        u = User(username=username, first_name=STAFF_NAMES[username])
        u.set_unusable_password()
        u.save()
        StaffAccess.objects.create(user=u, **perms)
        staff[username] = u
    clerk = staff["demo_clerk"]

    s = School.get()
    s.name, s.name_urdu = "Nexora Model School", "نیکسورا ماڈل سکول"
    s.address, s.phone, s.motto = "12-B Education Avenue, Model Town, Lahore", "042-3500-0000", "LEARN • LEAD • GROW"
    s.show_expenses, s.last_backup_at = True, timezone.now()
    s.save()

    access.set_current_user(owner)
    teachers = []
    for i, (name, g, qual, subj, salary) in enumerate(TEACHERS):
        teachers.append(Teacher.objects.create(
            name=name, gender=g, qualification=qual, subjects=subj, salary=salary, phone=_phone(r), cnic=_cnic(r),
            father_name=r.choice(FATHERS), address=f"{r.randint(1, 400)}-{r.choice('ABCDEF')} {r.choice(AREAS)}, Lahore",
            joining_date=today.replace(year=today.year - r.randint(1, 8), month=r.randint(1, 12), day=1)))
    left_teacher = Teacher.objects.create(name="Ms. Sobia Iqbal", gender="F", qualification="M.A. English", subjects="English",
                                          salary=30000, status=Teacher.Status.LEFT, phone=_phone(r),
                                          joining_date=today.replace(year=today.year - 4, month=4, day=1),
                                          left_on=today.replace(month=3, day=31))
    class_teachers = [8, 8, 9, 9, 10, 10, 12, 12, 11, 4, 0, 1, 3]

    classes = []
    for i, (name, fee, _age) in enumerate(CLASSES):
        c = ClassRoom.objects.create(name=name, order=i + 1, colour=CLASS_COLOURS[i % len(CLASS_COLOURS)], default_fee=fee,
                                     class_teacher=teachers[class_teachers[i]])
        group = "early" if i < 3 else "primary" if i < 8 else "middle" if i < 11 else "senior"
        for j, subj in enumerate(SUBJECTS[group]):
            Subject.objects.create(classroom=c, name=subj, order=j)
        classes.append((c, group))

    # Students
    students = []
    for idx, (c, group) in enumerate(classes):
        age = CLASSES[idx][2]
        for roll in range(1, r.randint(11, 15) + 1):
            girl = r.random() < 0.47
            father = r.choice(FATHERS)
            surname = father.split()[-1] if r.random() < 0.6 else ""
            first = r.choice(GIRLS if girl else BOYS)
            name = f"{first} {surname}".strip() if surname and surname != first else f"{first} {r.choice(['Fatima', 'Noor', 'Ali', 'Ahmed', 'Hassan'])}" if r.random() < .4 else first
            years_here = r.randint(0, min(idx, 6))
            adm = today.replace(year=today.year - years_here, month=4, day=r.randint(1, 20)) if years_here else \
                today.replace(month=4, day=r.randint(1, 25))
            disc = r.choice([0] * 7 + [300, 500, 1000])
            st = Student.objects.create(
                name=name, father_name=father, mother_name=r.choice(MOTHERS), gender="F" if girl else "M",
                date_of_birth=dt.date(today.year - age - 1, r.randint(1, 12), r.randint(1, 28)),
                b_form_no=_cnic(r), father_cnic=_cnic(r), phone=_phone(r),
                address=f"House {r.randint(1, 300)}, Street {r.randint(1, 30)}, {r.choice(AREAS)}, Lahore",
                blood_group=r.choice(["A+", "B+", "O+", "AB+", "B-", "O-", ""]), classroom=c, roll_no=roll,
                admission_date=adm, monthly_fee=CLASSES[idx][1], discount=disc,
                remarks="Sibling discount" if disc else "")
            st._ability = r.uniform(0.45, 0.97)
            students.append(st)
    left = r.choice([x for x in students if x.classroom.order > 5])
    left.status, left.left_on, left.remarks = Student.Status.LEFT, today - dt.timedelta(days=40), "Family moved to Islamabad"
    left.save()
    active = [x for x in students if x.status == Student.Status.ACTIVE]

    # Fees for this school year (April → this month) and payments
    start = session_start(today)
    months, m = [], month_start(start)
    while m <= month_start(today):
        months.append(m)
        m = add_months(m, 1)
    late_payers = set(r.sample([x.pk for x in active], k=len(active) // 14))
    for st in active:
        for mo in months:
            fee = Fee.objects.create(student=st, month=mo, amount=st.monthly_fee, discount=st.discount)
            current = mo == months[-1]
            behind = st.pk in late_payers and mo >= months[-2]
            if current:
                pay = r.random() < 0.93 and not behind
            else:
                pay = not behind and r.random() < 0.97
            if pay:
                paid_on = mo + dt.timedelta(days=r.randint(0, 12) if r.random() < 0.85 else r.randint(13, 24))
                paid_on = min(paid_on, today)
                access.set_current_user(clerk if r.random() < 0.7 else owner)
                if r.random() < 0.08:
                    FeePayment.objects.create(fee=fee, amount=fee.net // 2, paid_on=paid_on, note="Part payment")
                else:
                    FeePayment.objects.create(fee=fee, amount=fee.net, paid_on=paid_on)
    access.set_current_user(owner)

    # Paper fund for Class 9 and 10 this month (added to the fee), and a few separate fines
    paper_month = Fee.objects.filter(month=months[-1], student__classroom__name__in=["Class 9", "Class 10"])
    for fee in paper_month:
        Charge.objects.create(student=fee.student, kind=Charge.Kind.PAPER, amount=800, reason="Board practice papers",
                              date=today.replace(day=1), fee=fee, created_by=owner, batch="demo-paper", batch_label="Paper fund · Class 9–10")
        fee.refresh_extra()
    for st in r.sample(active, 6):
        ch = Charge.objects.create(student=st, kind=r.choice([Charge.Kind.LATE, Charge.Kind.ABSENT]), amount=r.choice([100, 200]),
                                   reason="", date=today - dt.timedelta(days=r.randint(2, 20)), created_by=owner)
        if r.random() < 0.5:
            access.set_current_user(clerk)
            ch.receive(on=min(ch.date + dt.timedelta(days=2), today))
            access.set_current_user(owner)

    # Salaries: each month's salary is paid early the next month; this month is still to pay.
    prev = add_months(months[0], -1)  # last month of the previous school year, paid in April
    for t in teachers:
        Salary.objects.create(teacher=t, month=prev, amount=t.salary, paid_amount=t.salary,
                              paid_on=min(months[0] + dt.timedelta(days=r.randint(0, 4)), today))
    for t in teachers:
        for mo in months:
            sal = Salary.objects.create(teacher=t, month=mo, amount=t.salary)
            if mo != months[-1]:
                sal.paid_amount, sal.paid_on = t.salary, min(add_months(mo, 1) + dt.timedelta(days=r.randint(0, 4)), today)
                sal.save()

    # Expenses
    for mo in months:
        for cat, desc, amt in (("Rent", "Building rent", 85000), ("Electricity bill", "LESCO bill", r.randint(18, 42) * 1000),
                               ("Gas bill", "SNGPL bill", r.randint(2, 6) * 1000), ("Internet / phone", "Broadband", 3500),
                               ("Stationery", "Registers, chalk and markers", r.randint(3, 9) * 1000)):
            Expense.objects.create(date=min(mo + dt.timedelta(days=r.randint(4, 20)), today), category=cat, description=desc, amount=amt)
    Expense.objects.create(date=today - dt.timedelta(days=12), category="Events", description="Sports day prizes", amount=9000)

    # Tests and marks
    term_date = months[max(len(months) - 2, 0)] + dt.timedelta(days=14)
    for c, group in classes:
        kids = [x for x in active if x.classroom_id == c.pk]
        for kind, name, when, full in ((Test.Kind.TERM1, f"1st term {today.year}", term_date, 100),
                                       (Test.Kind.MONTHLY, f"{today:%B} monthly test", today - dt.timedelta(days=5), 25)):
            if when > today:
                continue
            test = Test.objects.create(classroom=c, kind=kind, name=name, date=when)
            for j, subj in enumerate(SUBJECTS[group]):
                ts = TestSubject.objects.create(test=test, name=subj, full_marks=full, order=j)
                for k in kids:
                    absent = r.random() < 0.02
                    score = None if absent else round(max(0.15, min(1.0, r.gauss(k._ability, 0.08))) * full * 2) / 2
                    Mark.objects.create(subject=ts, student=k, obtained=score, absent=absent)
            for k in kids:
                if k._ability > 0.88:
                    TestRemark.objects.create(test=test, student=k, text="Excellent work, keep it up!")
                elif k._ability < 0.55:
                    TestRemark.objects.create(test=test, student=k, text="Needs more practice at home.")

    # Attendance for the last four weeks
    days = _school_days(today - dt.timedelta(days=27), today)
    access.set_current_user(clerk)
    att = []
    for d in days:
        for st in active:
            x = r.random()
            att.append(StudentAttendance(student=st, date=d, status="A" if x < 0.04 else "L" if x < 0.06 else "P", marked_by=clerk))
    StudentAttendance.objects.bulk_create(att)
    TeacherAttendance.objects.bulk_create([
        TeacherAttendance(teacher=t, date=d, status="T" if r.random() < 0.05 else "L" if r.random() < 0.03 else "P", marked_by=clerk)
        for d in days for t in teachers])
    access.set_current_user(owner)

    # Certificates
    senior = [x for x in active if x.classroom.name == "Class 10"][:1]
    for st in senior:
        data = C.clean_data("CHAR", C.initial_for_student("CHAR", st))
        Certificate.objects.create(kind="CHAR", student=st, person_name=st.name, issued_on=today - dt.timedelta(days=3), data=data)
    data = C.clean_data("SLC", C.initial_for_student("SLC", left))
    data["reason"] = "Family moved to another city"
    Certificate.objects.create(kind="SLC", student=left, person_name=left.name, issued_on=left.left_on, data=data)
    data = C.clean_data("EXP", C.initial_for_teacher("EXP", left_teacher))
    Certificate.objects.create(kind="EXP", teacher=left_teacher, person_name=left_teacher.name, issued_on=left_teacher.left_on, data=data)

    ActivityLog.add("settings", "Demo school created with fictional records")
    access.set_current_user(None)
