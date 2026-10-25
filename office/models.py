"""
All records of the school (Nexora School Office).

    School        - name, address, phone, logo, grading (one row)
    ClassRoom     - Play Group ... Class 10, each with its own colour and subjects
    Subject       - subjects of a class (written by the admin)
    Student       - student file, own monthly fee and discount, auto admission no.
    Teacher       - staff file and fixed monthly salary
    Fee           - one student's fee for one month (part payments allowed)
    FeePayment    - money received against a Fee, with its receipt number
    Salary        - one teacher's salary for one month, paid or not
    Test          - a monthly test or term exam for one class
    TestSubject   - a subject in that test and its full marks
    Mark          - marks obtained by one student in one test subject
    TestRemark    - remarks for one student in one test
    Expense       - other money spent (rent, bills ...), optional on the profit page
    ActivityLog   - "Recent activity": everything that was done, by whom, newest first
    StaffAccess   - what each office staff login is allowed to do (the owner can do everything)
    StudentAttendance / TeacherAttendance - daily attendance (Present, Absent, Leave, Late)
    PromotionBatch / ClassHistory - yearly promotion to the next class (kept for history, can be undone)
    Certificate   - certificates and letters issued, with their serial number
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

MONEY = dict(max_digits=10, decimal_places=0, default=0, validators=[MinValueValidator(0)])


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def session_start(d, start_month=4):
    """The school year runs April-March: the session containing date d starts on this date."""
    year = d.year if d.month >= start_month else d.year - 1
    return date(year, start_month, 1)


def next_number(model, field, prefix, width):
    last = (model.objects.filter(**{f"{field}__startswith": prefix})
            .order_by(f"-{field}").values_list(field, flat=True).first())
    seq = 1
    if last:
        try:
            seq = int(last[len(prefix):]) + 1
        except ValueError:
            seq = model.objects.filter(**{f"{field}__startswith": prefix}).count() + 1
    return f"{prefix}{seq:0{width}d}"


class Gender(models.TextChoices):
    MALE = "M", "Male"
    FEMALE = "F", "Female"


# ---------------------------------------------------------------------------
# School (single row)
# ---------------------------------------------------------------------------
DEFAULT_GRADES = "90 A+\n80 A\n70 B\n60 C\n50 D\n40 E\n0 F"


class School(models.Model):
    name = models.CharField(max_length=120, default="Nexora Model School")
    name_urdu = models.CharField(max_length=120, blank=True, default="نیکسورا ماڈل سکول")
    address = models.CharField(max_length=250, blank=True, default="12-B Education Avenue, Model Town, Lahore")
    phone = models.CharField(max_length=60, blank=True, default="042-3500-0000")
    motto = models.CharField(max_length=150, blank=True)
    logo = models.ImageField(upload_to="logo/", blank=True,
                             help_text="Leave empty to use the school logo that came with the system.")
    pass_percent = models.PositiveSmallIntegerField(default=40, validators=[MaxValueValidator(100)])
    grade_scale = models.TextField(
        default=DEFAULT_GRADES,
        help_text="One grade per line: the lowest percentage, a space, then the grade. Highest first.",
    )
    fee_due_day = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(1), MaxValueValidator(28)],
        help_text="Day of the month printed as the last date on fee challans.",
    )
    letterhead = models.ImageField(
        upload_to="letterhead/", blank=True,
        help_text="Optional: a picture of the school letterhead (top part). Used at the top of certificates.")
    UI_SIZES = [("normal", "Normal"), ("large", "Large"), ("xlarge", "Extra large")]
    ui_size = models.CharField("Button and text size", max_length=8, choices=UI_SIZES, default="normal")
    backup_folder = models.CharField(max_length=400, blank=True)
    last_backup_at = models.DateTimeField(null=True, blank=True)
    show_expenses = models.BooleanField(default=False)

    class Meta:
        verbose_name = "school"

    def __str__(self):
        return self.name

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def grades(self):
        """[(min_percent, grade), ...] highest first."""
        out = []
        for line in self.grade_scale.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                try:
                    out.append((float(parts[0]), parts[1].strip()))
                except ValueError:
                    continue
        return sorted(out, reverse=True) or [(0, "-")]

    def grade_for(self, percent):
        if percent is None:
            return "-"
        for minimum, grade in self.grades():
            if percent >= minimum:
                return grade
        return self.grades()[-1][1]


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------
class Teacher(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Working"
        LEFT = "LEFT", "Left"

    name = models.CharField(max_length=100)
    father_name = models.CharField("Father's / husband's name", max_length=100, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    cnic = models.CharField("CNIC", max_length=20, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=250, blank=True)
    qualification = models.CharField(max_length=120, blank=True)
    subjects = models.CharField("Subjects taught", max_length=200, blank=True)
    joining_date = models.DateField(null=True, blank=True)
    salary = models.DecimalField("Monthly salary", **MONEY)
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.ACTIVE)
    left_on = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("office:teacher_detail", args=[self.pk])


# ---------------------------------------------------------------------------
# Classes & subjects
# ---------------------------------------------------------------------------
CLASS_COLOURS = [
    "#e4572e", "#f3a712", "#a8c256", "#2e86ab", "#7b2cbf", "#2a9d8f", "#e76f51",
    "#457b9d", "#c9184a", "#6a994e", "#bc6c25", "#3a0ca3", "#118ab2", "#8d6e63",
]


class ClassRoom(models.Model):
    name = models.CharField(max_length=40, unique=True)
    order = models.PositiveSmallIntegerField(default=0, help_text="Position in lists (Play Group = 1 …)")
    colour = models.CharField(max_length=7, default="#2e86ab",
                              validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Pick a colour.")])
    default_fee = models.DecimalField("Usual monthly fee", **MONEY,
                                      help_text="Filled in automatically when you admit a new student to this class.")
    class_teacher = models.ForeignKey(Teacher, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="class_teacher_of")

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "class"
        verbose_name_plural = "classes"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("office:class_detail", args=[self.pk])

    @property
    def active_students(self):
        return self.students.filter(status=Student.Status.ACTIVE)


class Subject(models.Model):
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=60)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        unique_together = ("classroom", "name")

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
class Student(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Studying"
        INACTIVE = "INACTIVE", "Not attending"
        LEFT = "LEFT", "Left school"
        PASSED = "PASSED", "Passed out"

    BLOOD_GROUPS = [(g, g) for g in ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]]

    admission_no = models.CharField("Admission no.", max_length=20, unique=True, editable=False)
    name = models.CharField("Student name", max_length=100)
    father_name = models.CharField("Father's name", max_length=100, blank=True)
    mother_name = models.CharField("Mother's name", max_length=100, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    b_form_no = models.CharField("B-Form no.", max_length=25, blank=True)
    father_cnic = models.CharField("Father's CNIC", max_length=20, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=250, blank=True)
    photo = models.ImageField(upload_to="students/", blank=True)
    previous_school = models.CharField(max_length=150, blank=True)
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUPS, blank=True)
    medical_notes = models.CharField("Medical notes", max_length=250, blank=True)

    classroom = models.ForeignKey(ClassRoom, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="students", verbose_name="Class")
    roll_no = models.PositiveIntegerField("Roll no.", null=True, blank=True)
    admission_date = models.DateField(null=True, blank=True, default=date.today)
    monthly_fee = models.DecimalField(**MONEY)
    discount = models.DecimalField("Monthly discount", **MONEY)

    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    left_on = models.DateField("Left on", null=True, blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["classroom__order", "roll_no", "name"]

    def __str__(self):
        return f"{self.name} ({self.admission_no})"

    def save(self, *args, **kwargs):
        if not self.admission_no:
            year = (self.admission_date or timezone.localdate()).year
            with transaction.atomic():
                self.admission_no = next_number(Student, "admission_no", f"{settings.ADMISSION_PREFIX}-{year}-", 4)
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("office:student_detail", args=[self.pk])

    @property
    def net_fee(self):
        return max(self.monthly_fee - self.discount, 0)

    @property
    def initials(self):
        bits = [b for b in self.name.split() if b]
        return "".join(b[0] for b in bits[:2]).upper() or "?"

    @property
    def so_do(self):
        return "D/o" if self.gender == "F" else "S/o"

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        t, b = timezone.localdate(), self.date_of_birth
        return t.year - b.year - ((t.month, t.day) < (b.month, b.day))

    def unpaid_fees(self):
        return [f for f in self.fees.prefetch_related("payments").order_by("month") if f.balance > 0]

    def balance_due(self):
        return sum((f.balance for f in self.fees.prefetch_related("payments")), Decimal(0))


# ---------------------------------------------------------------------------
# Fees
# ---------------------------------------------------------------------------
class Fee(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="fees")
    month = models.DateField(help_text="Stored as the 1st of the month")
    amount = models.DecimalField("Fee", **MONEY)
    discount = models.DecimalField(**MONEY)
    extra = models.DecimalField("Paper fund / fines added", **MONEY, editable=False,
                                help_text="Total of the paper fund and fines added to this month (kept up to date automatically).")
    note = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month", "student"]
        unique_together = ("student", "month")

    def __str__(self):
        return f"{self.student.name} — {self.month:%B %Y}"

    def save(self, *args, **kwargs):
        self.month = month_start(self.month)
        super().save(*args, **kwargs)

    @property
    def tuition(self):
        return max(self.amount - self.discount, 0)

    @property
    def net(self):
        """What is to be paid for this month: tuition after discount, plus any paper fund / fines added to it."""
        return self.tuition + (self.extra or 0)

    def refresh_extra(self):
        total = self.charges.aggregate(s=models.Sum("amount"))["s"] or 0
        if total != self.extra:
            self.extra = total
            self.save(update_fields=["extra"])

    @property
    def paid(self):
        # works with prefetch_related("payments")
        return sum((p.amount for p in self.payments.all()), Decimal(0))

    @property
    def balance(self):
        return max(self.net - self.paid, 0)

    @property
    def status(self):
        if self.net == 0 or self.paid >= self.net:
            return "PAID"
        return "PART" if self.paid > 0 else "UNPAID"

    @property
    def status_label(self):
        return {"PAID": "Paid", "PART": "Part paid", "UNPAID": "Unpaid"}[self.status]


class FeePayment(models.Model):
    fee = models.ForeignKey(Fee, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=0, validators=[MinValueValidator(1)])
    paid_on = models.DateField(default=date.today)
    receipt_no = models.CharField(max_length=20, unique=True, editable=False)
    note = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+", editable=False)

    class Meta:
        ordering = ["-paid_on", "-id"]

    def __str__(self):
        return f"{self.receipt_no} Rs. {self.amount}"

    @property
    def received_by_name(self):
        from .access import display_name
        return display_name(self.received_by) if self.received_by_id else ""

    def save(self, *args, **kwargs):
        if not self.pk and not self.received_by_id:
            from .access import current_user
            self.received_by = current_user()
        if not self.receipt_no:
            with transaction.atomic():
                self.receipt_no = next_number(FeePayment, "receipt_no", f"R-{self.paid_on:%Y}-", 5)
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Salaries
# ---------------------------------------------------------------------------
class Salary(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="salaries")
    month = models.DateField()
    amount = models.DecimalField("Salary", **MONEY)
    paid_amount = models.DecimalField(**MONEY)
    paid_on = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=150, blank=True)
    slip_no = models.CharField(max_length=20, blank=True, editable=False)

    class Meta:
        ordering = ["-month", "teacher__name"]
        unique_together = ("teacher", "month")

    def __str__(self):
        return f"{self.teacher.name} — {self.month:%B %Y}"

    def save(self, *args, **kwargs):
        self.month = month_start(self.month)
        if not self.slip_no:
            self.slip_no = next_number(Salary, "slip_no", f"S-{self.month:%Y}-", 4)
        super().save(*args, **kwargs)

    @property
    def balance(self):
        return max(self.amount - self.paid_amount, 0)

    @property
    def status(self):
        if self.amount and self.paid_amount >= self.amount:
            return "PAID"
        return "PART" if self.paid_amount > 0 else "UNPAID"

    @property
    def status_label(self):
        return {"PAID": "Paid", "PART": "Part paid", "UNPAID": "Unpaid"}[self.status]


# ---------------------------------------------------------------------------
# Tests & results
# ---------------------------------------------------------------------------
class Test(models.Model):
    class Kind(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly test"
        TERM1 = "TERM1", "1st term"
        TERM2 = "TERM2", "2nd term"
        TERM3 = "TERM3", "3rd term"
        OTHER = "OTHER", "Other test"

    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name="tests", verbose_name="Class")
    kind = models.CharField("Type", max_length=8, choices=Kind.choices, default=Kind.MONTHLY)
    name = models.CharField(max_length=80, help_text='e.g. "October monthly test" or "1st term 2026"')
    date = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.name} — {self.classroom}"

    def get_absolute_url(self):
        return reverse("office:test_detail", args=[self.pk])


class TestSubject(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=60)
    full_marks = models.DecimalField(max_digits=6, decimal_places=1, default=100,
                                     validators=[MinValueValidator(Decimal("0.5"))])
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} ({self.full_marks:g})"


class Mark(models.Model):
    subject = models.ForeignKey(TestSubject, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="marks")
    obtained = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True,
                                   validators=[MinValueValidator(Decimal("0"))])
    absent = models.BooleanField(default=False)

    class Meta:
        unique_together = ("subject", "student")


class TestRemark(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="remarks")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="test_remarks")
    text = models.CharField(max_length=250, blank=True)

    class Meta:
        unique_together = ("test", "student")


# ---------------------------------------------------------------------------
# Other expenses
# ---------------------------------------------------------------------------
class Expense(models.Model):
    CATEGORIES = [(c, c) for c in ["Rent", "Electricity bill", "Gas bill", "Water bill", "Internet / phone",
                                   "Stationery", "Repairs", "Cleaning", "Events", "Transport", "Other"]]
    date = models.DateField(default=date.today)
    category = models.CharField(max_length=30, choices=CATEGORIES, default="Other")
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=0, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.category} Rs. {self.amount}"


# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------
class ActivityLog(models.Model):
    KINDS = [
        ("fee", "Fees"), ("student", "Students"), ("class", "Classes"), ("teacher", "Teachers"),
        ("salary", "Salaries"), ("test", "Tests"), ("expense", "Expenses"), ("certificate", "Certificates"),
        ("promotion", "Promotion"), ("backup", "Backup"), ("settings", "Settings"),
        ("attendance", "Attendance"), ("login", "Logins"), ("security", "Blocked / warnings"),
    ]
    at = models.DateTimeField(default=timezone.now, db_index=True)
    kind = models.CharField(max_length=12, choices=KINDS)
    text = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    link = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    who = models.CharField("Done by", max_length=60, blank=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return self.text

    @classmethod
    def add(cls, kind, text, amount=None, link=""):
        if hasattr(link, "get_absolute_url"):
            link = link.get_absolute_url()
        from .access import current_user, display_name
        user = current_user()
        return cls.objects.create(kind=kind, text=text[:300], amount=amount, link=link or "",
                                  user=user, who=display_name(user)[:60])


# ---------------------------------------------------------------------------
# Promotion to the next class (new school year)
# ---------------------------------------------------------------------------
class PromotionBatch(models.Model):
    session_year = models.PositiveSmallIntegerField(help_text="The new school year starts in April of this year")
    done_on = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)
    used_new_fee = models.BooleanField(default=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Promotion {self.session_year}-{(self.session_year + 1) % 100:02d}"


class ClassHistory(models.Model):
    class Result(models.TextChoices):
        PROMOTED = "PROMOTED", "Promoted"
        KEPT = "KEPT", "Kept in same class"
        PASSED = "PASSED", "Passed out"

    batch = models.ForeignKey(PromotionBatch, on_delete=models.CASCADE, related_name="entries")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="class_history")
    from_class = models.ForeignKey(ClassRoom, null=True, on_delete=models.SET_NULL, related_name="+")
    to_class = models.ForeignKey(ClassRoom, null=True, on_delete=models.SET_NULL, related_name="+")
    from_class_name = models.CharField(max_length=40, blank=True)
    to_class_name = models.CharField(max_length=40, blank=True)
    result = models.CharField(max_length=8, choices=Result.choices)
    old_roll = models.PositiveIntegerField(null=True, blank=True)
    old_fee = models.DecimalField(max_digits=10, decimal_places=0, default=0)
    new_fee = models.DecimalField(max_digits=10, decimal_places=0, default=0)
    old_status = models.CharField(max_length=8, blank=True)

    class Meta:
        ordering = ["-batch__session_year", "-id"]


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------
class Certificate(models.Model):
    class Kind(models.TextChoices):
        LEAVING = "SLC", "School Leaving Certificate"
        CHARACTER = "CHAR", "Character Certificate"
        BIRTH = "DOB", "Date of Birth Certificate"
        PASSED = "PASS", "Passing-out Certificate (Matric)"
        EXPERIENCE = "EXP", "Experience Certificate"
        RELIEVING = "REL", "Relieving Letter"
        APPRECIATION = "APP", "Appreciation Letter"

    STUDENT_KINDS = ["SLC", "CHAR", "DOB", "PASS"]
    TEACHER_KINDS = ["EXP", "REL", "APP"]

    kind = models.CharField(max_length=4, choices=Kind.choices)
    serial_no = models.CharField(max_length=20, unique=True, editable=False)
    student = models.ForeignKey(Student, null=True, blank=True, on_delete=models.SET_NULL, related_name="certificates")
    teacher = models.ForeignKey(Teacher, null=True, blank=True, on_delete=models.SET_NULL, related_name="certificates")
    person_name = models.CharField(max_length=100)
    issued_on = models.DateField(default=date.today)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_on", "-id"]

    def __str__(self):
        return f"{self.serial_no} {self.get_kind_display()} — {self.person_name}"

    def save(self, *args, **kwargs):
        if not self.serial_no:
            with transaction.atomic():
                self.serial_no = next_number(Certificate, "serial_no", f"{self.kind}-{self.issued_on:%Y}-", 3)
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Logins: what each office staff member may do
# ---------------------------------------------------------------------------
class StaffAccess(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_access")
    fees = models.BooleanField("Receive fees and print receipts", default=True)
    attendance = models.BooleanField("Mark attendance", default=True)
    students = models.BooleanField("Admit students and edit details", default=True)
    tests = models.BooleanField("Tests and results", default=False)
    certificates = models.BooleanField("Certificates", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Access for {self.user}"


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
class AttendanceStatus(models.TextChoices):
    PRESENT = "P", "Present"
    ABSENT = "A", "Absent"
    LEAVE = "L", "Leave"
    LATE = "T", "Late"


class StudentAttendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=1, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student.name} {self.date}: {self.get_status_display()}"


class TeacherAttendance(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=1, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    note = models.CharField(max_length=120, blank=True)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("teacher", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.teacher.name} {self.date}: {self.get_status_display()}"


# ---------------------------------------------------------------------------
# Paper fund and fines
# ---------------------------------------------------------------------------
class Charge(models.Model):
    """
    Paper fund or a fine for one student. Either added to a month's fee (then it is paid with the fee,
    on the same challan and receipt) or kept separate (its own slip and its own receipt).
    """
    class Kind(models.TextChoices):
        PAPER = "PAPER", "Paper fund"
        LATE = "LATE", "Late fee fine"
        ABSENT = "ABSENT", "Absence fine"
        OTHER = "OTHER", "Other fine"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="charges")
    kind = models.CharField("Type", max_length=6, choices=Kind.choices, default=Kind.PAPER)
    amount = models.DecimalField(max_digits=10, decimal_places=0, validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=150, blank=True)
    date = models.DateField(default=date.today)
    fee = models.ForeignKey(Fee, null=True, blank=True, on_delete=models.SET_NULL, related_name="charges",
                            help_text="Set when it was added to a month's fee.")
    paid_on = models.DateField(null=True, blank=True)
    receipt_no = models.CharField(max_length=20, null=True, blank=True, unique=True, editable=False)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+", editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    batch = models.CharField(max_length=40, blank=True, db_index=True, editable=False,
                             help_text="Same value for everything added together (e.g. a whole class at once).")
    batch_label = models.CharField(max_length=80, blank=True, editable=False)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} Rs. {self.amount} — {self.student.name}"

    @property
    def label(self):
        return f"{self.get_kind_display()}{f' ({self.reason})' if self.reason else ''}"

    @property
    def with_fee(self):
        return self.fee_id is not None

    @property
    def status(self):
        if self.with_fee:
            return "WITHFEE"
        return "PAID" if self.paid_on else "UNPAID"

    @property
    def received_by_name(self):
        from .access import display_name
        return display_name(self.received_by) if self.received_by_id else ""

    def receive(self, on=None):
        """Mark a separate charge as paid, with its own receipt number."""
        from .access import current_user
        self.paid_on = on or timezone.localdate()
        self.received_by = current_user()
        with transaction.atomic():
            self.receipt_no = next_number(Charge, "receipt_no", f"C-{self.paid_on:%Y}-", 5)
            self.save(update_fields=["paid_on", "received_by", "receipt_no"])
